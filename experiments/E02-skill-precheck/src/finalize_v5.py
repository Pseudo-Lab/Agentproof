"""Offline provenance freeze and shared N/C2 schema export after a completed v5 run."""
import hashlib
import json
import platform
import sys
from pathlib import Path
from run import write_json

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]


def freeze_sources(root,snapshot,files,expected):
    payloads={rel:(root/rel).read_bytes() for rel in files}
    hashes={rel:hashlib.sha256(data).hexdigest() for rel,data in payloads.items()}
    mismatch=[rel for rel in files if rel in expected and hashes[rel]!=expected[rel]]
    if mismatch:raise ValueError(f'run-time source changed before snapshot: {mismatch}')
    changed=[rel for rel,data in payloads.items()
             if (snapshot/rel).exists() and (snapshot/rel).read_bytes()!=data]
    if changed:raise ValueError(f'existing snapshot is immutable: {changed}')
    for rel,data in payloads.items():
        dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():dest.write_bytes(data)
    return hashes


def finalize(folder):
    folder=Path(folder);m=json.loads((folder/'manifest.json').read_text())
    if not m.get('finished_at_utc'):raise ValueError('real run still active')
    rows=[json.loads(l) for l in (folder/'trials.jsonl').read_text().splitlines()]
    snapshot=folder/'code_snapshot'
    files=['src/agent_v5.py','src/run_v5.py','src/analyze_v5.py','src/agent.py','src/tasks.py',
           'src/openai_http.py','src/run.py','src/analyze.py','src/w6_report.py','src/test_v5.py',
           'configs/plan_v5_report.json','configs/model.json','analysis/V5_PROTOCOL.md']
    skills=[str(p.relative_to(EXP)) for p in (EXP/'skills').glob('*/SKILL.md')]
    expected=dict(m['hashes'])
    expected.update({f'skills/{task}/SKILL.md':h for task,h in m['skill_hashes'].items()})
    hashes=freeze_sources(EXP,snapshot,files+skills,expected)
    m.update(experiment_id='E02-skill-precheck',run_id=folder.name,model=m['model_config']['model'],
             code_snapshot='code_snapshot',snapshot_hashes=hashes,
             environment=dict(python=sys.version,platform=platform.platform(),sandbox='Python -I subprocess; not network-isolated'),
             cost_basis='USD Standard list price; input 0.75/M, output4.50/M; cache discount omitted; checked2026-11-09',
             seed_policy='five fresh input seeds; model temperature and sampling seed not transmitted')
    write_json(folder/'manifest.json',m)
    out=folder/'shared_N_vs_C2';out.mkdir(exist_ok=True)
    cfg=dict(m);cfg.update(task_ids=[f'{t}@{e}@L3' for t in m['plan']['tasks'] for e in m['plan']['envs']],
                         code_snapshot='../code_snapshot',
                         repeats_per_condition=dict(baseline=5,intervention=5),
                         comparison=dict(baseline='N neutral pre/post',intervention='C2 premise+workspace listing, neutral post'),
                         repeat_unit='fresh input instance, not same-input stochastic reliability')
    write_json(out/'manifest.json',cfg)
    shared=[]
    for r in rows:
        if r['loc']!='L3' or r['cond'] not in ('N','C2'):continue
        shared.append(dict(run_id=m['run_id'],task_id=f'{r["task"]}@{r["env"]}@L3',
                           condition='baseline' if r['cond']=='N' else 'intervention',repeat_id=r['repeat_id'],
                           status=r['status'],score=int(r['status']=='success'),latency_ms=r['latency_s']*1000,
                           input_tokens=r['usage']['input_tokens'],output_tokens=r['usage']['output_tokens'],
                           cost_usd=r['cost_usd'],missing_reasons={},
                           evidence=dict(trace=f'../traces/{r["trial_id"]}/trace.json',input_seed=r['input_seed'],
                                         final=r['final'],condition_label=r['cond'])))
    (out/'trials.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in shared))
    sys.path.insert(0,str(ROOT/'harness'));from summarize import summarize
    summary=summarize(out);write_json(out/'summary.json',summary)
    print(f'frozen {len(files)} sources; validated {len(shared)} shared trials')

if __name__=='__main__':finalize(sys.argv[1])
