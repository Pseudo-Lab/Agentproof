"""Run E02 v4 trials on SkillsBench tasks.

  python3 sb/run_sb.py --plan sb/plan_pilot.json --run-id pilot-sb-001 --sb-root ~/Documents/ChatGPT/Agentproof/skillsbench

Per trial: fresh container (network none) -> skills for (env, cond) at /root/.claude/skills -> agent loop
-> official verifier (bridge network attached only for the verifier) -> container removed.
Success = verifier reward 1.0 (all tests pass) and the agent finished normally.
Outputs results/sb/<stage>/<run-id>/ (manifest, trials.jsonl, analysis.json, traces/).
"""
import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import common as C
import docker_env as D
import agent_sb as AG
from analyze_sb import analyze

MAX_CONSECUTIVE_INFRA = 3
TASK_SUFFIX = ('\n\n---\n이 과제에 쓸 수 있는 스킬(작업 절차서)이 제공될 수 있으니 read_skill로 먼저 확인하세요. '
               '스킬 파일은 /root/.claude/skills 아래에 있습니다.')


class Budget:
    def __init__(self, cap):
        self.cap, self.spent, self.lock = cap, 0.0, threading.Lock()

    def can_spend(self, worst):
        with self.lock:
            return self.spent + worst <= self.cap

    def spend(self, usd):
        with self.lock:
            self.spent += usd


def opened_any(trace, needles):
    blob = ' '.join((i.get('arguments') or '') for i in trace if i.get('type') == 'function_call')
    return any(n in blob for n in needles)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--sb-root', required=True, type=Path)
    p.add_argument('--env-file', default=str(C.ROOT / '.env'))
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        p.error('bad run-id')
    plan = json.loads(args.plan.read_text())
    cfg = C.load_tasks_config()
    tasks = {t['name']: t for t in cfg['tasks'] if t['name'] in plan['tasks']}
    missing = set(plan['tasks']) - set(tasks)
    if missing:
        p.error(f'tasks not in tasks.json: {missing}')
    model_cfg = json.loads((C.SB / plan['model_config']).read_text())
    limits = AG.Limits(model_cfg['limits'])
    out = C.EXPERIMENT / 'results' / 'sb' / plan['stage'] / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    (out / 'traces').mkdir()

    from openai_http import HTTPClient, load_key
    client = HTTPClient(load_key(args.env_file), timeout_s=300)

    images, metas = {}, {}
    for name in plan['tasks']:
        td = args.sb_root / 'tasks' / name
        metas[name] = D.parse_task_md(td / 'task.md')
        images[name] = D.build_image(td, name, cfg['sb_commit'])

    rng = random.Random(plan['order_seed'])
    order = []
    for rep in range(1, plan['repeats'] + 1):
        blocks = [(t, e) for t in plan['tasks'] for e in plan['envs']]
        rng.shuffle(blocks)
        for t, e in blocks:
            conds = list(plan['conditions'])
            rng.shuffle(conds)
            order += [(t, e, c, rep) for c in conds]

    sb_head = subprocess.run(['git', '-C', str(args.sb_root), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    manifest = {
        'experiment_id': 'E02-skill-precheck', 'design_version': 'v4-skillsbench', 'run_id': args.run_id,
        'stage': plan['stage'], 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'code_commit': subprocess.run(['git', '-C', str(C.ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
        'code_dirty': bool(subprocess.run(['git', '-C', str(C.ROOT), 'status', '--porcelain'], capture_output=True, text=True).stdout.strip()),
        'skillsbench_commit_pinned': cfg['sb_commit'], 'skillsbench_checkout_head': sb_head,
        'model': model_cfg['model'], 'model_config': model_cfg, 'plan': plan,
        'images': images, 'execution_order': [f'{t}@{e}/{c}/r{r}' for t, e, c, r in order],
        'hashes': {'hook_C': C.sha(AG.HOOK_C), 'hook_C2': C.sha(AG.HOOK_C2), 'hook_post': C.sha(AG.HOOK_POST),
                   'system_prompt': C.sha(AG.SYSTEM_PROMPT), 'tools': C.sha(json.dumps(AG.TOOLS, sort_keys=True)),
                   'tasks_json': C.sha((C.SB / 'tasks.json').read_text()),
                   'agent_sb_py': C.sha((C.SB / 'agent_sb.py').read_text())},
        'environment': {'python': sys.version, 'agent_network': 'none', 'verifier_network': 'bridge',
                        'container_limits': 'cpus<=2, memory<=3072MB'},
        'seed_policy': 'temperature/seed not sent; order_seed fixed', 'parallel_workers': plan['workers'],
        'budget_usd': plan['budget_usd'],
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    budget = Budget(plan['budget_usd'])
    lock = threading.Lock()
    rows = []
    state = {'consecutive_infra': 0, 'stop': False}

    def trial(spec):
        name, env, cond, rep = spec
        if state['stop']:
            return
        tid = f'{name}-{env}-{cond}-r{rep}'
        tcfg, (meta, body) = tasks[name], metas[name]
        tdir = out / 'traces' / tid
        tdir.mkdir()
        row = {'run_id': args.run_id, 'trial_id': tid, 'task': name, 'env': env, 'cond': cond, 'repeat_id': rep}
        cont = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                skill_text = C.materialize_skills(args.sb_root / 'tasks' / name, tcfg, env, cond, Path(tmp) / 'skills')
                cont = D.Container(images[name], D.workdir_of(images[name], meta),
                                   meta.get('sandbox.cpus', 2), meta.get('sandbox.memory_mb', 4096))
                if skill_text is not None:
                    cont.put_dir(Path(tmp) / 'skills', C.SKILL_ROOT_IN_CONTAINER)
                row['skill_sha'] = C.sha(skill_text) if skill_text else None
                res = AG.run_agent(client, model_cfg, limits, body + TASK_SUFFIX, AG.make_executor(cont, skill_text),
                                   cond, budget)
                ver = cont.run_verifier(args.sb_root / 'tasks' / name / 'verifier',
                                        timeout=int(min(meta.get('verifier.timeout_sec', 900), 1200)))
        except Exception as exc:
            res, ver = None, None
            row.update({'status': 'error', 'stop_reason': 'infra_error', 'error': f'{type(exc).__name__}: {str(exc)[:400]}'})
        finally:
            if cont:
                cont.remove()
        if res is not None:
            u = res['usage']
            cost = (u['input_tokens'] * model_cfg['price_input_per_mtok'] + u['output_tokens'] * model_cfg['price_output_per_mtok']) / 1e6
            reward = ver['reward']
            if res['stop_reason'] in ('api_error', 'budget_cap'):
                status = 'error'
            elif res['stop_reason'] != 'agent_finished':
                status = 'timeout'
            else:
                status = 'success' if reward is not None and reward >= 0.999 else 'failure'
            row.update({'status': status, 'reward': reward, 'tests': ver['tests'], 'stop_reason': res['stop_reason'],
                        'error': res['error'], 'latency_ms': round(res['elapsed_s'] * 1000),
                        'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
                        'reasoning_tokens': u['reasoning_tokens'], 'cached_input_tokens': u['cached_input_tokens'],
                        'cost_usd': round(cost, 6), 'model_requests': res['model_requests'], 'tool_calls': res['tool_calls'],
                        'pre_hooks': res['pre_hooks'], 'post_hooks': res['post_hooks'],
                        'evidence_opened': opened_any(res['trace'], tcfg.get('evidence_needles', [])),
                        'forbidden_hits': res['forbidden_hits']})
            (tdir / 'trace.json').write_text(json.dumps({'trial_id': tid, 'final_text': res['final_text'],
                                                         'response_ids': res['response_ids'], 'items': res['trace']},
                                                        ensure_ascii=False, indent=1))
            (tdir / 'verifier.json').write_text(json.dumps(ver, ensure_ascii=False, indent=1))
        with lock:
            rows.append(row)
            infra = row['stop_reason'] in ('api_error', 'infra_error')
            state['consecutive_infra'] = state['consecutive_infra'] + 1 if infra else 0
            if state['consecutive_infra'] >= MAX_CONSECUTIVE_INFRA:
                state['stop'] = True
            if row['stop_reason'] == 'budget_cap':
                state['stop'] = True
            with (out / 'trials.jsonl').open('a') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f"[{len(rows):3d}/{len(order)}] {tid:48s} {row['status']:8s} r={row.get('reward')} "
                  f"ev={int(row.get('evidence_opened', 0))} tools={row.get('tool_calls')} ${row.get('cost_usd', 0):.4f} "
                  f"{row.get('stop_reason')} {(row.get('error') or '')[:80]}", flush=True)

    with ThreadPoolExecutor(max_workers=plan['workers']) as ex:
        list(ex.map(trial, order))

    manifest.update({'finished_at_utc': datetime.now(timezone.utc).isoformat(), 'completed_trials': len(rows),
                     'planned_trials': len(order), 'spent_usd_estimate': round(budget.spent, 4),
                     'stopped_early': state['stop']})
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (out / 'analysis.json').write_text(json.dumps(analyze(rows, plan), ensure_ascii=False, indent=2))
    print(out)


if __name__ == '__main__':
    main()
