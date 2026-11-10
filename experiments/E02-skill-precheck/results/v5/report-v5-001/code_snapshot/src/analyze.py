"""E02 analysis (v3): pre-registered contrasts, per-cell counts, mechanism and cost.

  python3 src/analyze.py results/<stage>/<run-id>

Pre-registered (CARD.md, fixed before any v3 run):
  P1  E1·L3   C2 − B   location-guided check recovers an unpointed mismatch      (expect > 0)
  P2  E1·L3   C  − B   generic check does not (replicates pilot-003)             (expect ≈ 0)
  S1  E0      C2 − B   side effect when the skill fits (L2+L3 pooled)            (expect ≈ 0)
  S2  E0      C  − B   same for the generic check                                (expect ≈ 0)
  M1  E1·B    L2 − L3  manipulation check: pointing to evidence helps B          (expect > 0)
Intervals: Wilson per rate, Newcombe for differences. They treat trials as independent; trials
are clustered in 3 tasks, so per-task counts are reported next to every pooled number.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

PREREG = [
    ('P1', 'E1', 'L3', 'C2', 'B', 'location-guided check vs baseline, unpointed mismatch'),
    ('P2', 'E1', 'L3', 'C', 'B', 'generic check vs baseline, unpointed mismatch'),
    ('S1', 'E0', None, 'C2', 'B', 'location-guided check side effect, skill fits'),
    ('S2', 'E0', None, 'C', 'B', 'generic check side effect, skill fits'),
]


def wilson(s, n, z=1.96):
    if n == 0:
        return None
    p = s / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def newcombe(s1, n1, s2, n2):
    if not n1 or not n2:
        return None
    p1, p2 = s1 / n1, s2 / n2
    (l1, u1), (l2, u2) = wilson(s1, n1), wilson(s2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def _pp(x):
    return None if x is None else round(100 * x, 1)


def analyze(rows, plan):
    def select(env=None, loc=None, cond=None, task=None):
        return [r for r in rows if (env is None or r['env'] == env) and (loc is None or r['loc'] == loc)
                and (cond is None or r['cond'] == cond) and (task is None or r['task'] == task)]

    def succ(rs):
        return sum(r['status'] == 'success' for r in rs)

    def contrast(env, loc, a, b):
        ra, rb = select(env, loc, a), select(env, loc, b)
        nc = newcombe(succ(ra), len(ra), succ(rb), len(rb))
        per_task = {t: f"{succ(select(env, loc, a, t))}/{len(select(env, loc, a, t))} vs "
                       f"{succ(select(env, loc, b, t))}/{len(select(env, loc, b, t))}" for t in plan['tasks']}
        return {'a': f'{succ(ra)}/{len(ra)}', 'b': f'{succ(rb)}/{len(rb)}',
                'diff_pp': _pp(nc[0]) if nc else None,
                'ci95_pp': [_pp(nc[1]), _pp(nc[2])] if nc else None, 'per_task': per_task}

    result = {'design_version': 'v3', 'preregistered': {}}
    for key, env, loc, a, b, desc in PREREG:
        if a in plan['conditions'] and b in plan['conditions']:
            result['preregistered'][key] = {'desc': desc, 'env': env, 'loc': loc or 'L2+L3',
                                            'contrast': f'{a} - {b}', **contrast(env, loc, a, b)}
    if 'B' in plan['conditions'] and {'L2', 'L3'} <= set(plan['locs']):
        r2, r3 = select('E1', 'L2', 'B'), select('E1', 'L3', 'B')
        nc = newcombe(succ(r2), len(r2), succ(r3), len(r3))
        result['preregistered']['M1'] = {'desc': 'manipulation check: B with pointed vs unpointed evidence (E1)',
                                         'a': f'{succ(r2)}/{len(r2)}', 'b': f'{succ(r3)}/{len(r3)}',
                                         'diff_pp': _pp(nc[0]) if nc else None,
                                         'ci95_pp': [_pp(nc[1]), _pp(nc[2])] if nc else None}

    cells = []
    for task in plan['tasks']:
        for env in plan['envs']:
            for loc in plan['locs']:
                entry = {'task': task, 'env': env, 'loc': loc}
                for c in plan['conditions']:
                    rs = select(env, loc, c, task)
                    if rs:
                        entry[c] = {'success': succ(rs), 'n': len(rs),
                                    'evidence_opened': sum(r['evidence_opened'] for r in rs),
                                    'listed_workspace': sum(r['listed_workspace'] for r in rs),
                                    'grade_reasons': dict(Counter(r['grade_reason'] for r in rs))}
                cells.append(entry)
    result['cells'] = cells

    # mechanism: success conditional on opening the evidence file
    mech = {}
    for c in plan['conditions']:
        for env in plan['envs']:
            for loc in plan['locs']:
                rs = select(env, loc, c)
                if rs:
                    op = [r for r in rs if r['evidence_opened']]
                    no = [r for r in rs if not r['evidence_opened']]
                    mech[f'{c}|{env}|{loc}'] = {'opened': f'{len(op)}/{len(rs)}',
                                                'success_if_opened': f'{succ(op)}/{len(op)}',
                                                'success_if_not_opened': f'{succ(no)}/{len(no)}'}
    result['mechanism'] = mech

    by_cond = {}
    for c in plan['conditions']:
        rs = select(cond=c)
        if not rs:
            continue
        by_cond[c] = {'trials': len(rs), 'success': succ(rs),
                      'mean_cost_usd': round(sum(r['cost_usd'] for r in rs) / len(rs), 5),
                      'total_cost_usd': round(sum(r['cost_usd'] for r in rs), 4),
                      'mean_tool_calls': round(sum(r['tool_calls'] for r in rs) / len(rs), 2),
                      'mean_input_tokens': round(sum(r['input_tokens'] for r in rs) / len(rs)),
                      'mean_output_tokens': round(sum(r['output_tokens'] for r in rs) / len(rs)),
                      'mean_latency_s': round(sum(r['latency_ms'] for r in rs) / len(rs) / 1000, 1),
                      'hook_counts': dict(Counter(r['hook_count'] for r in rs)),
                      'errors': sum(r['status'] == 'error' for r in rs),
                      'limit_stops': sum(r['status'] == 'timeout' for r in rs),
                      'input_modified': sum(r['input_modified'] for r in rs),
                      'leak_flagged': sum(bool(r['leak_flags']) for r in rs)}
    result['by_condition'] = by_cond
    result['total_cost_usd'] = round(sum(r['cost_usd'] for r in rows), 4)
    result['n_trials'] = len(rows)
    result['notes'] = [
        'success = required output passes all checks and the run ended normally; limit stops and errors count as 0',
        'CIs assume independent trials; trials are clustered in 3 tasks (see per_task)',
        f"repeats per cell: {plan['repeats']}; tasks: {len(plan['tasks'])}",
    ]
    return result


if __name__ == '__main__':
    run = Path(sys.argv[1])
    rows = [json.loads(l) for l in (run / 'trials_all.jsonl').read_text().splitlines() if l.strip()]
    plan = json.loads((run / 'manifest.json').read_text())['plan']
    print(json.dumps(analyze(rows, plan), ensure_ascii=False, indent=2))
