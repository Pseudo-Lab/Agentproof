"""E02 v4 analysis: pre-registered contrasts with task-cluster bootstrap, per-task counts, mechanism, cost.

  python3 sb/analyze_sb.py results/sb/<stage>/<run-id>

Unit of inference is the task: CIs come from resampling tasks with replacement (10,000 draws),
computing the pooled success-rate difference each time. Per-task counts are always reported.
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

PREREG = [
    ('H1', 'E1', 'C2', 'B', 'premise-targeted pre-check vs baseline, mismatched skill'),
    ('H2', 'E1', 'P', 'C2', 'adding a post-check on top of the pre-check, mismatched skill'),
    ('H3', 'E1', 'C', 'B', 'generic pre-check vs baseline (v2/v3 replication), mismatched skill'),
    ('H4', 'E1', 'S', 'B', 'skill-side boundary section vs baseline, mismatched skill'),
    ('H5', 'E1', 'P', 'S', 'harness-side (pre+post) vs skill-side'),
    ('S1', 'E0', 'C2', 'B', 'side effect of the pre-check when the skill fits'),
    ('S2', 'E0', 'P', 'B', 'side effect of pre+post when the skill fits'),
    ('S3', 'E0', 'S', 'B', 'side effect of the skill-side section when the skill fits'),
    ('M1', None, 'B', 'B', 'manipulation check: B in E0 minus B in E1 (computed specially)'),
]


def _succ(rows):
    return sum(r['status'] == 'success' for r in rows)


def cluster_bootstrap(by_task_a, by_task_b, tasks, draws=10_000, seed=0):
    rng = random.Random(seed)
    diffs = []
    for _ in range(draws):
        pick = [rng.choice(tasks) for _ in tasks]
        sa = sum(by_task_a[t][0] for t in pick); na = sum(by_task_a[t][1] for t in pick)
        sb = sum(by_task_b[t][0] for t in pick); nb = sum(by_task_b[t][1] for t in pick)
        if na and nb:
            diffs.append(sa / na - sb / nb)
    diffs.sort()
    if not diffs:
        return None
    return diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]


def analyze(rows, plan):
    valid = [r for r in rows if r['status'] != 'error']
    tasks = list(plan['tasks'])

    def counts(env, cond):
        d = {}
        for t in tasks:
            rs = [r for r in valid if r['task'] == t and r['env'] == env and r['cond'] == cond]
            d[t] = (_succ(rs), len(rs))
        return d

    out = {'design_version': 'v4-skillsbench', 'n_trials': len(rows), 'n_errors_excluded': len(rows) - len(valid),
           'preregistered': {}}
    conds = set(plan['conditions'])
    for key, env, a, b, desc in PREREG:
        if key == 'M1':
            if 'B' in conds and set(plan['envs']) >= {'E0', 'E1'}:
                ca, cb = counts('E0', 'B'), counts('E1', 'B')
            else:
                continue
        else:
            if a not in conds or b not in conds or env not in plan['envs']:
                continue
            ca, cb = counts(env, a), counts(env, b)
        sa, na = sum(v[0] for v in ca.values()), sum(v[1] for v in ca.values())
        sb, nb = sum(v[0] for v in cb.values()), sum(v[1] for v in cb.values())
        diff = (sa / na - sb / nb) if na and nb else None
        ci = cluster_bootstrap(ca, cb, tasks) if na and nb else None
        out['preregistered'][key] = {
            'desc': desc, 'env': env or 'E0 vs E1', 'contrast': f'{a} - {b}',
            'a': f'{sa}/{na}', 'b': f'{sb}/{nb}', 'diff_pp': None if diff is None else round(100 * diff, 1),
            'ci95_pp_task_bootstrap': None if ci is None else [round(100 * ci[0], 1), round(100 * ci[1], 1)],
            'per_task': {t: f'{ca[t][0]}/{ca[t][1]} vs {cb[t][0]}/{cb[t][1]}' for t in tasks},
            'tasks_a_better': sum(ca[t][0] / ca[t][1] > cb[t][0] / cb[t][1] for t in tasks if ca[t][1] and cb[t][1]),
            'tasks_b_better': sum(ca[t][0] / ca[t][1] < cb[t][0] / cb[t][1] for t in tasks if ca[t][1] and cb[t][1]),
        }

    cells = defaultdict(dict)
    for t in tasks:
        for env in plan['envs']:
            for c in plan['conditions']:
                rs = [r for r in valid if r['task'] == t and r['env'] == env and r['cond'] == c]
                if rs:
                    cells[f'{t}|{env}'][c] = {
                        'success': _succ(rs), 'n': len(rs),
                        'mean_reward': round(sum((r.get('reward') or 0) for r in rs) / len(rs), 3),
                        'evidence_opened': sum(bool(r.get('evidence_opened')) for r in rs),
                        'status': dict(Counter(r['status'] for r in rs))}
    out['cells'] = cells

    mech = {}
    for env in plan['envs']:
        for c in plan['conditions']:
            rs = [r for r in valid if r['env'] == env and r['cond'] == c]
            op = [r for r in rs if r.get('evidence_opened')]
            no = [r for r in rs if not r.get('evidence_opened')]
            if rs:
                mech[f'{c}|{env}'] = {'opened': f'{len(op)}/{len(rs)}', 'success_if_opened': f'{_succ(op)}/{len(op)}',
                                      'success_if_not': f'{_succ(no)}/{len(no)}'}
    out['mechanism'] = mech

    by_cond = {}
    for c in plan['conditions']:
        rs = [r for r in valid if r['cond'] == c]
        if not rs:
            continue
        by_cond[c] = {'trials': len(rs), 'success': _succ(rs),
                      'mean_cost_usd': round(sum(r['cost_usd'] for r in rs) / len(rs), 5),
                      'mean_tool_calls': round(sum(r['tool_calls'] for r in rs) / len(rs), 2),
                      'mean_latency_s': round(sum(r['latency_ms'] for r in rs) / len(rs) / 1000, 1),
                      'status': dict(Counter(r['status'] for r in rs)),
                      'pre_hooks': dict(Counter(r['pre_hooks'] for r in rs)),
                      'post_hooks': dict(Counter(r['post_hooks'] for r in rs)),
                      'forbidden_hits': sum(r.get('forbidden_hits', 0) for r in rs)}
    out['by_condition'] = by_cond
    out['errors'] = dict(Counter((r.get('error') or '')[:120] for r in rows if r['status'] == 'error'))
    out['total_cost_usd'] = round(sum(r.get('cost_usd', 0) for r in rows), 4)
    return out


if __name__ == '__main__':
    run = Path(sys.argv[1])
    rows = [json.loads(l) for l in (run / 'trials.jsonl').read_text().splitlines() if l.strip()]
    plan = json.loads((run / 'manifest.json').read_text())['plan']
    print(json.dumps(analyze(rows, plan), ensure_ascii=False, indent=2))
