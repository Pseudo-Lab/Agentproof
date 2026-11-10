"""Exploratory v5 analysis. Three task families remain three task families."""
import json
import random
import sys
from collections import Counter
from pathlib import Path
from w6_report import cluster_difference,validate_rows


def analyze(rows,plan):
    if rows and 'trial_id' in rows[0]:validate_rows(rows)
    cells={};n_expected=len(plan['input_seeds'])
    for task in plan['tasks']:
        for env in plan['envs']:
            for loc in ('L2','L3'):
                for cond in plan['pointed_conditions'] if loc=='L2' else plan['hidden_conditions']:
                    rs=[r for r in rows if (r['task'],r['env'],r['loc'],r['cond'])==(task,env,loc,cond)]
                    cells['/'.join((task,env,loc,cond))]=dict(
                        success=sum(r['status']=='success' for r in rs),n=len(rs),expected=n_expected,
                        labels=dict(Counter(r['final']['label'] for r in rs)),
                        errors=sum(r['status']=='error' for r in rs),
                        explicit_evidence_reads=sum(r.get('explicit_evidence_read',False) for r in rs))
    contrasts={}
    for env in plan['envs']:
        selected=[r for r in rows if r['env']==env and r['loc']=='L3']
        for a,b in [('C2','N'),('C2','B'),('V','N'),('P','C2'),('P','V'),('P','N'),('N','B')]:
            ready=all(cells[f'{task}/{env}/L3/{cond}']['n']==n_expected
                      for task in plan['tasks'] for cond in (a,b))
            contrasts[f'{a}-{b}|{env}']=dict(complete=ready,
                effect=cluster_difference(selected,a,b,seed=20261110) if ready else None)
    transitions={};by_cond={}
    for cond in plan['hidden_conditions']:
        for env in plan['envs']:
            rs=[r for r in rows if r['cond']==cond and r['env']==env and r['loc']=='L3']
            transitions[f'{cond}|{env}']=dict(Counter(
                f'{r["before_post"]["label"]} -> {r["final"]["label"]}' if r['before_post'] else
                'no_first_completion' for r in rs))
        rs=[r for r in rows if r['cond']==cond and r['loc']=='L3']
        by_cond[cond]=dict(n=len(rs),success=sum(r['status']=='success' for r in rs),
                          cost_usd=round(sum(r['cost_usd'] for r in rs),8),
                          mean_cost_usd=round(sum(r['cost_usd'] for r in rs)/len(rs),8) if rs else None,
                          mean_tool_calls=sum(r.get('tool_calls',0) for r in rs)/len(rs) if rs else None)
    transitions_by_task={}
    for task in plan['tasks']:
        for cond in plan['hidden_conditions']:
            for env in plan['envs']:
                rs=[r for r in rows if (r['task'],r['cond'],r['env'],r['loc'])==(task,cond,env,'L3')]
                transitions_by_task[f'{task}|{cond}|{env}']=dict(Counter(
                    f'{r["before_post"]["label"]} -> {r["final"]["label"]}' if r['before_post'] else
                    'no_first_completion' for r in rs))
    resources={}
    for cond in plan['hidden_conditions']:
        rs=[r for r in rows if r['cond']==cond and r['loc']=='L3']
        resources[cond]=dict(n=len(rs),input_tokens=sum(r.get('usage',{}).get('input_tokens',0) for r in rs),
                            output_tokens=sum(r.get('usage',{}).get('output_tokens',0) for r in rs),
                            requests=sum(r.get('model_requests',0) for r in rs),
                            tools=sum(r.get('tool_calls',0) for r in rs),
                            stops=dict(Counter(r.get('stop_reason','unknown') for r in rs)))
    interactions={}
    for name in ('C2-N','V-N','P-N'):
        a=contrasts[f'{name}|E1']['effect'];b=contrasts[f'{name}|E0']['effect']
        if a and b:
            values={t:a['per_task_pp'][t]-b['per_task_pp'][t] for t in plan['tasks']}
            rng=random.Random(20261110);v=list(values.values())
            draws=sorted(sum(rng.choices(v,k=len(v)))/len(v) for _ in range(10000))
            interactions[name]=dict(diff_pp=round(sum(v)/len(v),2),ci95_pp=[round(draws[249],2),round(draws[9749],2)],per_task_pp=values)
        else:interactions[name]=None
    manipulation={}
    for env in plan['envs']:
        for task in plan['tasks']:
            manipulation[f'{task}|{env}']={loc:cells[f'{task}/{env}/{loc}/B'] for loc in ('L2','L3')}
    return dict(design_version='v5-report-controlled',n_trials=len(rows),
                complete=all(v['n']==v['expected'] for v in cells.values()),cells=cells,
                comparisons=contrasts,interactions=interactions,transitions=transitions,
                by_condition_hidden=by_cond,manipulation=manipulation,
                transitions_by_task=transitions_by_task,resources_hidden=resources,
                cost_usd=round(sum(r['cost_usd'] for r in rows),8),
                unknown_billing_upper_usd=sum(r.get('unknown_billing_upper_usd',0) for r in rows),
                inference='Exploratory. Equal task-family weighting, 3 families only. Bootstrap intervals are descriptive, '
                          'not confirmation or a general non-inferiority guarantee. No outcome feedback given to agent.')

if __name__=='__main__':
    p=Path(sys.argv[1]);m=json.loads((p/'manifest.json').read_text())
    rs=[json.loads(l) for l in (p/'trials.jsonl').read_text().splitlines() if l.strip()]
    print(json.dumps(analyze(rs,m['plan']),ensure_ascii=False,indent=2))
