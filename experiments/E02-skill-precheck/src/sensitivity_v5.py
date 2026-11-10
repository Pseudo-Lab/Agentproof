"""Post-hoc offline sensitivity and exhaustive post-hook behavior audit. No API calls.

The exact paired test is conditional on the fixed task/input pairs and exchangeable
independent discordance signs, not a task-population significance test.
"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path, PurePosixPath
import tasks as T

EXP=Path(__file__).resolve().parents[1]


def paired_contrast(rows,a,b,env='E1',loc='L3'):
    pairs={}
    for row in rows:
        if row['env']!=env or row['loc']!=loc or row['cond'] not in (a,b):continue
        key=(row['task'],row['input_seed'])
        cell=pairs.setdefault(key,{})
        if row['cond'] in cell:raise ValueError(f'duplicate pair cell: {key}, {row["cond"]}')
        cell[row['cond']]=row['status']=='success'
    if not pairs or any(set(cell)!={a,b} for cell in pairs.values()):
        raise ValueError('missing paired condition')
    both=sum(cell[a] and cell[b] for cell in pairs.values())
    neither=sum(not cell[a] and not cell[b] for cell in pairs.values())
    ao=sum(cell[a] and not cell[b] for cell in pairs.values())
    bo=sum(cell[b] and not cell[a] for cell in pairs.values())
    discordant=ao+bo
    p=min(1.,2*sum(math.comb(discordant,i) for i in range(min(ao,bo)+1))/2**discordant) if discordant else 1.
    return dict(a=a,b=b,n_pairs=len(pairs),task_families=len({t for t,s in pairs}),
                a_only=ao,b_only=bo,both_success=both,both_failure=neither,
                diff_pp=round(100*(ao-bo)/len(pairs),2),exact_two_sided_p=p,
                scope='Post-hoc fixed-input paired sensitivity; assumes independent pairs and exchangeable discordance signs. '
                      'Does not establish task-population significance or harmlessness.')


def leave_one_out(task_effects):
    if len(task_effects)<2:raise ValueError('at least two task families required')
    return dict(full_mean_pp=round(sum(task_effects.values())/len(task_effects),2),
                without={task:round(sum(v for t,v in task_effects.items() if t!=task)/(len(task_effects)-1),2)
                         for task in sorted(task_effects)})


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def post_behavior(folder,row,prompts):
    td=folder/'traces'/row['trial_id'];trace=json.loads((td/'trace.json').read_text())['trace']
    text=prompts['POST'] if row['cond'] in ('V','P') else prompts['NEUTRAL_POST']
    indices=[i for i,item in enumerate(trace) if item.get('role')=='developer' and item.get('content')==text]
    if len(indices)!=1:raise ValueError(f'post hook not exactly once: {row["trial_id"]}')
    items=trace[indices[0]+1:]
    outputs={i['call_id']:i.get('output','') for i in items if i.get('type')=='function_call_output'}
    calls=[]
    for item in items:
        if item.get('type')!='function_call':continue
        args=json.loads(item.get('arguments') or '{}');result=outputs.get(item['call_id'])
        calls.append(dict(name=item['name'],arguments=args,result=result))
    explicit_evidence=[];output_reads=[];writes=[];python=[]
    for call in calls:
        args=call['arguments'];path=PurePosixPath(args.get('path','')).as_posix().removeprefix('./')
        successful=call['result'] is not None and not call['result'].startswith('ERROR:')
        if call['name']=='read_file' and successful:
            if path==T.EVIDENCE_PATH[row['task']]:explicit_evidence.append(path)
            if path.startswith('output/'):output_reads.append(path)
        if call['name']=='write_file' and successful:writes.append(path)
        if call['name']=='run_python':
            python.append(dict(code=args.get('code',''),result=call['result'],
                               successful=bool(call['result'] and call['result'].startswith('exit=0\n'))))
    name=Path(T.OUTPUT_FILE[row['task']]).name
    before=file_sha(td/'before_post'/name);after=file_sha(td/'output'/name)
    return dict(trial_id=row['trial_id'],task=row['task'],env=row['env'],cond=row['cond'],
                first_label=row['before_post']['label'] if row['before_post'] else None,
                final_label=row['final']['label'],tool_calls=dict(Counter(c['name'] for c in calls)),
                no_post_tools=not calls,explicit_successful_evidence_reads=explicit_evidence,
                explicit_successful_output_reads=output_reads,successful_write_file_calls=writes,
                python_calls=python,required_artifact_changed=before!=after,
                before_sha256=before,final_sha256=after)


def main():
    folder=EXP/'results/v5/report-v5-001'
    m=json.loads((folder/'manifest.json').read_text())
    rows=[json.loads(l) for l in (folder/'trials.jsonl').read_text().splitlines()]
    a=json.loads((folder/'analysis.json').read_text())
    details=[post_behavior(folder,r,m['prompts']) for r in rows if r['loc']=='L3' and r['cond']!='B']
    groups={}
    for cond in ('N','C2','V','P'):
        for env in ('E0','E1'):
            rs=[r for r in details if r['cond']==cond and r['env']==env]
            calls=Counter()
            for r in rs:calls.update(r['tool_calls'])
            groups[f'{cond}/{env}']=dict(
                n=len(rs),no_tool_trials=sum(r['no_post_tools'] for r in rs),tool_call_totals=dict(calls),
                evidence_read_trials=sum(bool(r['explicit_successful_evidence_reads']) for r in rs),
                output_read_trials=sum(bool(r['explicit_successful_output_reads']) for r in rs),
                python_trials=sum(bool(r['python_calls']) for r in rs),
                write_file_trials=sum(bool(r['successful_write_file_calls']) for r in rs),
                artifact_changed_trials=sum(r['required_artifact_changed'] for r in rs),
                wrong_to_correct=sum(r['first_label']!='correct' and r['final_label']=='correct' for r in rs))
    result=dict(analysis_status='post-hoc supplementary, no new model execution',
                paired_c2_n=paired_contrast(rows,'C2','N'),
                leave_one_family_out=leave_one_out(a['comparisons']['C2-N|E1']['effect']['per_task_pp']),
                post_groups=groups,post_trial_details=details,
                caveat='Explicit successful read_file is a lower bound. Python programs and returns must be manually audited; '
                       'absence of a path substring alone is not proof of no evidence access. Behavior categories overlap.')
    dest=EXP/'analysis/v5_sensitivity.json';dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='post_trial_details'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
