"""V5 controlled study. Imports never call APIs. --mock is offline plumbing only."""
import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import agent_v5 as V
import tasks as T
from run import env_hash, git, sha, write_json

EXP=Path(__file__).resolve().parents[1]


def order_for(plan):
    rng=random.Random(plan['order_seed']);out=[]
    for rep,seed in enumerate(plan['input_seeds'],1):
        blocks=[(t,e,l) for t in plan['tasks'] for e in plan['envs'] for l in ('L2','L3')]
        rng.shuffle(blocks)
        for task,env,loc in blocks:
            conds=list(plan['hidden_conditions'] if loc=='L3' else plan['pointed_conditions'])
            rng.shuffle(conds)
            out.extend((task,env,loc,c,rep,seed) for c in conds)
    return out


def remaining_cap(plan):
    ledger=[]
    prior_paths=list(plan['prior_runs'])
    # A new run-id never grants a fresh session allowance. Account for all earlier real v5 runs.
    for previous in sorted((EXP/'results/v5').glob('*/manifest.json')):
        previous_manifest=json.loads(previous.read_text())
        if previous_manifest.get('execution_mode')=='real':
            prior_paths.append(str(previous.parent.relative_to(EXP)))
    for rel in prior_paths:
        folder=EXP/rel;m=json.loads((folder/'manifest.json').read_text())
        if not m.get('finished_at_utc'):
            raise ValueError(f'prior run still active: {rel}')
        f=folder/('trials_all.jsonl' if (folder/'trials_all.jsonl').exists() else 'trials.jsonl')
        rows=[json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        # Unknown-billing errors use full configured token limits conservatively.
        cfg=m['model_config'];lim=cfg['limits']
        unknown=sum((lim['max_cumulative_input_tokens']*cfg['price_input_per_mtok']+
                     lim['max_cumulative_output_tokens']*cfg['price_output_per_mtok'])/1e6
                    for r in rows if r.get('stop_reason')=='api_error')
        known=max(sum(r.get('cost_usd',0) for r in rows),m.get('spent_usd_estimate',0),m.get('conservative_spent_usd',0))
        if 'conservative_spent_usd' in m:unknown=0
        ledger.append(dict(path=rel,known_usd=known,unknown_billing_upper_usd=unknown))
    used=sum(r['known_usd']+r['unknown_billing_upper_usd'] for r in ledger)
    cap=min(plan['maximum_budget_usd'],plan['session_authorization_usd']-used-plan['reserve_usd'])
    if cap<=0:raise ValueError('no authorized budget remains')
    return cap,ledger


def archive_output(ws,destination):
    destination.mkdir(parents=True,exist_ok=True)
    if (ws/'output').is_dir():
        shutil.copytree(ws/'output',destination,dirs_exist_ok=True)


def collect_final(task,env,seed,ws,tdir,before):
    errors=[]
    try:final=V.diagnose(task,env,seed,ws)
    except Exception as exc:
        final=dict(label='other_error',target_pass=False,other_pass=False,reason='diagnostic_error')
        errors.append(f'diagnose: {type(exc).__name__}: {str(exc)[:200]}')
    try:modified=before!=env_hash(ws)
    except Exception as exc:
        modified=True;errors.append(f'input_hash: {type(exc).__name__}: {str(exc)[:200]}')
    try:archive_output(ws,tdir/'output')
    except Exception as exc:errors.append(f'archive: {type(exc).__name__}: {str(exc)[:200]}')
    return dict(final=final,input_modified=modified,archive_errors=errors)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,default=EXP/'configs/plan_v5_report.json')
    ap.add_argument('--run-id',required=True);ap.add_argument('--mock',action='store_true')
    args=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):ap.error('invalid run id')
    plan=json.loads(args.plan.read_text());order=order_for(plan)
    cfg=json.loads((EXP/'configs/model.json').read_text())
    cfg['limits'].update(max_model_requests=20,max_tool_calls=20,max_cumulative_input_tokens=150000,
                         max_cumulative_output_tokens=20000)
    cap,prior=(plan['maximum_budget_usd'],[]) if args.mock else remaining_cap(plan)
    if not args.mock:
        from openai_http import HTTPClient,load_key
        api_key=load_key(EXP.parents[1]/'.env')
    out=EXP/'results'/'v5'/args.run_id;out.mkdir(parents=True,exist_ok=False)
    (out/'traces').mkdir();budget=V.Budget(cap);lock=threading.Lock();rows=[]
    state=dict(stop=False,consecutive_errors=0)
    manifest=dict(design_version=plan['design_version'],execution_mode='mock' if args.mock else 'real',
                  started_at_utc=datetime.now(timezone.utc).isoformat(),code_commit=git('rev-parse','HEAD'),
                  code_dirty=bool(git('status','--porcelain')),model_config=cfg,plan=plan,
                  runtime_budget_usd=cap,prior_budget_ledger=prior,planned_trials=len(order),
                  hashes={f:sha(EXP/f) for f in ('src/agent_v5.py','src/run_v5.py','src/tasks.py',
                                                 'src/agent.py','analysis/V5_PROTOCOL.md')},
                  prompts={k:getattr(V,k) for k in ('AUTHORITY','TASK_PROMPT','PRE','POST','NEUTRAL_PRE','NEUTRAL_POST')},
                  skill_hashes={t:sha(T.skill_path(t)) for t in plan['tasks']},
                  execution_order=[list(s) for s in order])
    write_json(out/'manifest.json',manifest)

    def trial(spec):
        task,env,loc,cond,rep,seed=spec
        with lock:
            if state['stop']:return
        tid=f'{task}-{env}-{loc}-{cond}-i{seed}';tdir=out/'traces'/tid;tdir.mkdir()
        with tempfile.TemporaryDirectory(prefix='e02-v5-') as tmp:
            ws=T.build_workspace(task,env,loc,seed,Path(tmp)/'ws')
            (ws/'task.md').write_text(V.TASK_PROMPT+'\n')
            for f in ws.rglob('*'):
                if f.is_file() and (ws/'output') not in f.parents:f.chmod(0o444)
            before=env_hash(ws)
            def snapshot():
                d=V.diagnose(task,env,seed,ws)
                archive_output(ws,tdir/'before_post')
                return d
            transport=HTTPClient(api_key) if not args.mock else __import__('test_v5').Scripted(
                lambda mode: solve_for_mock(task,env,ws,mode))
            result=V.run_agent(transport,cfg,ws,T.skill_path(task).read_text(),cond,budget,snapshot)
            collected=collect_final(task,env,seed,ws,tdir,before)
            final=collected['final'];modified=collected['input_modified']
        status=('error' if collected['archive_errors'] or result['stop_reason'] in ('api_error','budget_cap','snapshot_error') else
                'timeout' if result['stop_reason']!='agent_finished' else
                'success' if final['target_pass'] and not modified else 'failure')
        u=result['usage'];cost=(u['input_tokens']*cfg['price_input_per_mtok']+u['output_tokens']*cfg['price_output_per_mtok'])/1e6
        ev=T.EVIDENCE_PATH[task]
        reads=any(r['successful'] and Path(r['path']).as_posix().removeprefix('./')==ev for r in result['explicit_reads'])
        row=dict(trial_id=tid,task=task,env=env,loc=loc,cond=cond,repeat_id=rep,input_seed=seed,status=status,
                 stop_reason=result['stop_reason'],error=result['error'],final=final,before_post=result['before_post'],
                 explicit_evidence_read=reads,input_modified=modified,leak_flags=result['leak_flags'],
                 archive_errors=collected['archive_errors'],
                 cost_usd=round(cost,8),unknown_billing_upper_usd=result['unknown_billing_upper_usd'],
                 usage=u,model_requests=result['model_requests'],tool_calls=result['tool_calls'],
                 pre_hooks=result['pre_hooks'],post_hooks=result['post_hooks'],latency_s=result['elapsed_s'])
        write_json(tdir/'trace.json',result)
        with lock:
            rows.append(row)
            with (out/'trials.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            state['consecutive_errors']=state['consecutive_errors']+1 if result['stop_reason']=='api_error' else 0
            if state['consecutive_errors']>=3 or result['stop_reason']=='budget_cap':state['stop']=True
            print(f'[{len(rows)}/{len(order)}] {tid} {status} {final["label"]} ${cost:.4f}',flush=True)

    with ThreadPoolExecutor(max_workers=1 if args.mock else plan['workers']) as pool:
        list(pool.map(trial,order))
    manifest.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),completed_trials=len(rows),
                    known_cost_usd=round(sum(r['cost_usd'] for r in rows),8),
                    conservative_spent_usd=budget.spent,unknown_billing_upper_usd=budget.unknown_cost,
                    stopped_early=state['stop'],budget_reservations_remaining=budget.reserved)
    write_json(out/'manifest.json',manifest)
    from analyze_v5 import analyze
    write_json(out/'analysis.json',analyze(rows,plan))
    print(out,flush=True)


def solve_for_mock(task,env,ws,mode):
    T.solve(task,env,ws,mode)
    return T.OUTPUT_FILE[task],(ws/T.OUTPUT_FILE[task]).read_text()

if __name__=='__main__':main()
