"""Run E02 trials from a plan file (v3: env x evidence location x condition).

  python3 src/run.py --plan configs/plan_pilot_v3.json --run-id mock-001 --mock   # offline, no API
  python3 src/run.py --plan configs/plan_pilot_v3.json --run-id pilot-004         # real API calls

Outputs results/<stage>/<run-id>/:
  manifest.json            settings, hashes, commit, execution order
  trials_all.jsonl         every trial (all conditions, E02 fields)
  trials.jsonl             B/C only, mapped to the shared AgentProof schema (baseline/intervention)
  summary.json             shared harness summary of trials.jsonl
  analysis.json            E02 analysis (pre-registered contrasts, cells, mechanism, cost)
  traces/<trial>/          model/tool items (encrypted reasoning removed) and final output files
Existing run ids are never overwritten. No automatic retries.
"""
import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parent
EXPERIMENT = SRC.parent
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / 'harness'))
import tasks as T
import agent as A
from analyze import analyze

COND_TO_SHARED = {'B': 'baseline', 'C': 'intervention'}
MAX_CONSECUTIVE_API_ERRORS = 3  # infra guard added after main-001 (network loss); not a design change
COND_CONFIG = {'A': 'reference', 'B': 'baseline', 'C': 'intervention', 'C2': 'intervention_loc'}


class Budget:
    def __init__(self, cap_usd):
        self.cap = cap_usd
        self.spent = 0.0

    def can_spend(self, worst_usd):
        return self.spent + worst_usd <= self.cap

    def spend(self, usd):
        self.spent += usd


def sha(path_or_text):
    data = path_or_text.encode() if isinstance(path_or_text, str) else Path(path_or_text).read_bytes()
    return hashlib.sha256(data).hexdigest()


def env_hash(ws):
    """Hash of every workspace file outside output/ (inputs, contract, evidence)."""
    h = hashlib.sha256()
    for p in sorted(Path(ws).rglob('*')):
        if p.is_file() and (Path(ws) / 'output') not in p.parents:
            h.update(str(p.relative_to(ws)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def git(*args):
    try:
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def evidence_opened(trace, path):
    """True if any tool call argument mentions the evidence file path (read_file or code)."""
    name = Path(path).name
    for item in trace:
        if item.get('type') == 'function_call' and (path in (item.get('arguments') or '')
                                                   or name in (item.get('arguments') or '')):
            return True
    return False


def listed_workspace(trace):
    """True if the agent listed directories (os.walk/listdir/glob/rglob) via run_python."""
    pat = re.compile(r'os\.walk|listdir|scandir|glob|rglob|iterdir')
    return any(item.get('type') == 'function_call' and item.get('name') == 'run_python'
               and pat.search(item.get('arguments') or '') for item in trace)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--mock', action='store_true', help='scripted offline client; no API calls')
    p.add_argument('--env-file', default=str(ROOT / '.env'))
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        p.error('run-id: letters, numbers, _ or - only')
    plan = json.loads(args.plan.read_text())
    for c in plan['conditions']:
        if c not in COND_CONFIG:
            p.error(f'unknown condition {c}')
    model_cfg = json.loads((EXPERIMENT / 'configs/model.json').read_text())
    limits = A.Limits(model_cfg['limits'])
    out = EXPERIMENT / 'results' / plan['stage'] / args.run_id
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        p.error('run-id already exists; choose a new one')
    (out / 'traces').mkdir()

    if args.mock:
        mode = 'mock'
    else:
        from openai_http import HTTPClient, load_key
        client = HTTPClient(load_key(args.env_file))
        mode = 'real'

    # blocks of (repeat, task, env, loc); condition order shuffled within each block
    rng = random.Random(plan['order_seed'])
    order = []
    for rep in range(1, plan['repeats'] + 1):
        for task in plan['tasks']:
            for env in plan['envs']:
                for loc in plan['locs']:
                    conds = list(plan['conditions'])
                    rng.shuffle(conds)
                    order += [(task, env, loc, c, rep) for c in conds]

    skills = {t: T.skill_path(t).read_text() for t in plan['tasks']}
    manifest = {
        'experiment_id': EXPERIMENT.name, 'design_version': 'v3', 'run_id': args.run_id, 'stage': plan['stage'],
        'execution_mode': mode, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'code_commit': git('rev-parse', 'HEAD'), 'code_dirty': bool(git('status', '--porcelain')),
        'model': model_cfg['model'] if mode == 'real' else 'mock-scripted-client',
        'model_config': model_cfg, 'plan': plan,
        'task_ids': [f'{t}@{e}@{l}' for t in plan['tasks'] for e in plan['envs'] for l in plan['locs']],
        'repeats_per_condition': {'baseline': plan['repeats'], 'intervention': plan['repeats']},
        'conditions': {c: json.loads((EXPERIMENT / f'configs/{COND_CONFIG[c]}.json').read_text())
                       for c in plan['conditions']},
        'hashes': {'skills': {t: sha(skills[t]) for t in skills},
                   'hook_C': sha(A.HOOK_MESSAGE), 'hook_C2': sha(A.HOOK_MESSAGE_LOC),
                   'system_prompt': sha(A.SYSTEM_PROMPT), 'task_prompt': sha(T.TASK_PROMPT),
                   'tools': sha(json.dumps(A.TOOLS, sort_keys=True)),
                   'tasks_py': sha(SRC / 'tasks.py'), 'agent_py': sha(SRC / 'agent.py')},
        'execution_order': [f'{t}@{e}@{l}/{c}/r{r}' for t, e, l, c, r in order],
        'seed_policy': 'model sampling seed/temperature not sent (not confirmed supported for this model); '
                       'input_seed and order_seed fixed in plan',
        'cost_basis': 'usage tokens x Standard list price in model.json; cached-input discount not applied (upper bound)',
        'latency_basis': 'wall clock per trial including tool execution',
        'environment': {'python': sys.version, 'platform': sys.platform,
                        'sandbox': 'run_python = subprocess python -I in a temp workspace, stripped env (no API key), '
                                   '30 s timeout; NOT network-isolated (deviation from design)'},
        'budget_usd': plan['budget_usd'],
    }
    write_json(out / 'manifest.json', manifest)

    budget = Budget(plan['budget_usd'])
    all_rows, shared_rows = [], []
    consecutive_errors = 0
    for task, env, loc, cond, rep in order:
        trial_id = f'{task}-{env}-{loc}-{cond}-r{rep}'
        with tempfile.TemporaryDirectory(prefix='e02-') as tmp:
            ws = T.build_workspace(task, env, loc, plan['input_seed'], Path(tmp) / 'ws')
            for f in ws.rglob('*'):
                if f.is_file() and (ws / 'output') not in f.parents:
                    f.chmod(0o444)
            before = env_hash(ws)
            skill_text = skills[task] if cond != 'A' else None
            if args.mock:
                def solve_fn(m, task=task, env=env, loc=loc, seed=plan['input_seed']):
                    scratch = Path(tmp) / f'mock-{m}'
                    T.build_workspace(task, env, loc, seed, scratch)
                    T.solve(task, env, scratch, m)
                    rel = T.OUTPUT_FILE[task]
                    return rel, (scratch / rel).read_text()
                client = A.MockClient(solve_fn)
            res = A.run_agent(client, model_cfg, limits, T.TASK_PROMPT, ws, skill_text, cond, budget)
            passed, reason = T.grade(task, env, plan['input_seed'], ws)
            input_modified = env_hash(ws) != before
            tdir = out / 'traces' / trial_id
            tdir.mkdir()
            if (ws / 'output').exists():
                shutil.copytree(ws / 'output', tdir / 'output')
        if res['stop_reason'] in ('api_error', 'budget_cap'):
            status = 'error'
        elif res['stop_reason'] != 'agent_finished':
            status = 'timeout'
        else:
            status = 'success' if passed else 'failure'
        u = res['usage']
        cost = (u['input_tokens'] * model_cfg['price_input_per_mtok'] +
                u['output_tokens'] * model_cfg['price_output_per_mtok']) / 1e6
        write_json(tdir / 'trace.json', {'trial_id': trial_id, 'response_ids': res['response_ids'],
                                         'final_text': res['final_text'], 'items': res['trace']})
        row = {'run_id': args.run_id, 'trial_id': trial_id, 'task': task, 'env': env, 'loc': loc, 'cond': cond,
               'task_id': f'{task}@{env}@{loc}', 'repeat_id': rep, 'status': status,
               'score': int(status == 'success'), 'grade_pass': passed, 'grade_reason': reason,
               'stop_reason': res['stop_reason'], 'error': res['error'],
               'latency_ms': round(res['elapsed_s'] * 1000, 1),
               'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
               'reasoning_tokens': u['reasoning_tokens'], 'cached_input_tokens': u['cached_input_tokens'],
               'cost_usd': round(cost, 6), 'model_requests': res['model_requests'], 'tool_calls': res['tool_calls'],
               'hook_count': res['hook_count'], 'evidence_opened': evidence_opened(res['trace'], T.EVIDENCE_PATH[task]),
               'listed_workspace': listed_workspace(res['trace']),
               'input_modified': input_modified, 'leak_flags': res['leak_flags'],
               'skill_hash': manifest['hashes']['skills'][task] if skill_text else None,
               'trace': f'traces/{trial_id}/trace.json'}
        all_rows.append(row)
        print(f"{trial_id:26s} {status:8s} {reason:24s} ev={int(row['evidence_opened'])} req={res['model_requests']:2d} "
              f"tools={res['tool_calls']:2d} hook={res['hook_count']} ${cost:.4f} {res['elapsed_s']:.1f}s", flush=True)
        if cond in COND_TO_SHARED:
            shared_rows.append({
                'run_id': args.run_id, 'task_id': row['task_id'], 'condition': COND_TO_SHARED[cond],
                'repeat_id': rep, 'status': status, 'score': row['score'], 'latency_ms': row['latency_ms'],
                'input_tokens': row['input_tokens'], 'output_tokens': row['output_tokens'],
                'cost_usd': row['cost_usd'], 'missing_reasons': {},
                'evidence': {'trace': row['trace'], 'grade_reason': reason, 'stop_reason': row['stop_reason'],
                             'hook_count': row['hook_count'], 'label': cond}})
        if res['stop_reason'] == 'budget_cap':
            print('budget cap reached; stopping run', flush=True)
            break
        consecutive_errors = consecutive_errors + 1 if res['stop_reason'] == 'api_error' else 0
        if consecutive_errors >= MAX_CONSECUTIVE_API_ERRORS:
            print(f'{consecutive_errors} consecutive API/infra errors; stopping run (incomplete, rerun with a new run-id)', flush=True)
            break

    with (out / 'trials_all.jsonl').open('w') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in all_rows)
    with (out / 'trials.jsonl').open('w') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in shared_rows)
    manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['completed_trials'] = len(all_rows)
    manifest['planned_trials'] = len(order)
    manifest['spent_usd_estimate'] = round(budget.spent, 6)
    write_json(out / 'manifest.json', manifest)
    if {'B', 'C'} <= set(plan['conditions']) and len(all_rows) == len(order):
        from summarize import summarize
        write_json(out / 'summary.json', summarize(out))
    write_json(out / 'analysis.json', analyze(all_rows, plan))
    print(out.relative_to(ROOT))


if __name__ == '__main__':
    main()
