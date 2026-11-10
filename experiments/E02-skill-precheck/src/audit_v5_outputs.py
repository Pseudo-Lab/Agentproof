"""API-free independent regrading of archived first/final outputs and hook accounting."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import agent_v5 as V


def audit(folder):
    folder=Path(folder);m=json.loads((folder/'manifest.json').read_text())
    if not m.get('finished_at_utc'):raise ValueError('run still active')
    rows=[json.loads(l) for l in (folder/'trials.jsonl').read_text().splitlines()]
    violations=[];checks=0
    for r in rows:
        td=folder/'traces'/r['trial_id'];trace=json.loads((td/'trace.json').read_text())
        for stage,record in [('output',r['final']),('before_post',r['before_post'])]:
            if record is None:continue
            with tempfile.TemporaryDirectory() as tmp:
                ws=Path(tmp);(ws/'output').mkdir()
                archive=td/stage
                if archive.is_dir():shutil.copytree(archive,ws/'output',dirs_exist_ok=True)
                actual=V.diagnose(r['task'],r['env'],r['input_seed'],ws)
                for field in ('label','target_pass','other_pass'):
                    checks+=1
                    if actual[field]!=record[field]:violations.append(f'{r["trial_id"]} {stage} {field}')
        checks+=2
        if trace['pre_hooks']>1 or trace['post_hooks']>1:violations.append(r['trial_id']+' repeated hook')
        if r['stop_reason']=='agent_finished' and r['post_hooks']!=int(r['cond']!='B'):
            violations.append(r['trial_id']+' missing completion opportunity')
        calls=[i for i in trace['trace'] if i.get('type')=='function_call']
        checks+=1
        if not calls or calls[0]['name']!='read_skill':violations.append(r['trial_id']+' first tool')
        checks+=1
        expected_success=(r['final']['target_pass'] and r['stop_reason']=='agent_finished'
                          and not r['input_modified'] and not r['archive_errors'])
        if (r['status']=='success')!=expected_success:violations.append(r['trial_id']+' status mismatch')
    return dict(run=folder.name,checks=checks,violations=violations,trials=len(rows),
                planned=m['planned_trials'],known_cost_usd=sum(r['cost_usd'] for r in rows),
                conservative_spent_usd=m['conservative_spent_usd'],
                reservations_remaining=m['budget_reservations_remaining'])

if __name__=='__main__':
    f=Path(sys.argv[1]);result=audit(f)
    (f/'artifact_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['violations']:raise SystemExit(1)
