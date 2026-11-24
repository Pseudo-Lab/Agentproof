"""W8 ablation and repeat-reliability tables for E02, computed from existing trial files only.

No model API calls. Reads results/<stage>/<run>/trials_all.jsonl and writes analysis/w8_ablation.json.

Conditions (plan main-002 / w6-v3 replication):
  A  no skill (reference)
  B  skill only (baseline)
  C  skill + generic pre-check instruction (instruction without location hint)   <- ablation: C2 minus location hint
  C2 skill + pre-check instruction + location hint (intervention)

Cells = task x env x loc (3 x 2 x 2 = 12). Repeats = repeat_id 1..5 (same input seed, model sampling not seeded).
pass^3 = share of cells where repeats 1, 2 and 3 all succeed (pre-declared: first three repeats).
pass^5 (all five repeats) is reported as an exploratory extra.
"""
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RUNS = {
    'main-002': EXP / 'results/main/main-002/trials_all.jsonl',
    'w6-v3-20261109': EXP / 'results/replication/w6-v3-20261109/trials_all.jsonl',
}
CONDS = ['A', 'B', 'C', 'C2']


def wilson(k, n, z=1.96):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)


def summarize(rows, cond):
    rs = [r for r in rows if r['cond'] == cond]
    n = len(rs)
    k = sum(r['score'] for r in rs)
    cost = sum(r['cost_usd'] for r in rs)
    tokens = sum(r['input_tokens'] + r['output_tokens'] for r in rs)
    cells = defaultdict(dict)
    for r in rs:
        cells[(r['task'], r['env'], r['loc'])][int(r['repeat_id'])] = r['score']
    per_repeat = defaultdict(lambda: [0, 0])
    for r in rs:
        per_repeat[int(r['repeat_id'])][0] += r['score']
        per_repeat[int(r['repeat_id'])][1] += 1
    rep_rates = [v[0] / v[1] for _, v in sorted(per_repeat.items()) if v[1]]
    pass3 = sum(1 for c in cells.values() if all(c.get(i) == 1 for i in (1, 2, 3)))
    pass5 = sum(1 for c in cells.values() if all(c.get(i) == 1 for i in (1, 2, 3, 4, 5)))
    e1l3 = [r for r in rs if r['env'] == 'E1' and r['loc'] == 'L3']
    k13 = sum(r['score'] for r in e1l3)
    lo, hi = wilson(k, n)
    return {
        'condition': cond, 'n': n, 'successes': k, 'success_rate': round(k / n, 3) if n else None,
        'wilson95': [lo, hi],
        'repeat_success_rates': [round(x, 3) for x in rep_rates],
        'repeat_sd_pp': round(statistics.stdev(rep_rates) * 100, 1) if len(rep_rates) > 1 else None,
        'pass3': f'{pass3}/{len(cells)}', 'pass5_exploratory': f'{pass5}/{len(cells)}',
        'E1_L3': f'{k13}/{len(e1l3)}',
        'cost_usd_total': round(cost, 4), 'cost_usd_per_trial': round(cost / n, 5) if n else None,
        'tokens_per_trial': round(tokens / n) if n else None,
        'cost_usd_per_success': round(cost / k, 5) if k else None,
    }


def contrast(rows, a, b):
    """Paired-by-cell difference a - b (pp), with task-level (cell-level) bootstrap-free descriptive summary."""
    def rate(c):
        rs = [r for r in rows if r['cond'] == c]
        return sum(r['score'] for r in rs) / len(rs) if rs else None
    ra, rb = rate(a), rate(b)
    return None if ra is None or rb is None else round((ra - rb) * 100, 1)


def cell_diffs(rows, a, b):
    out = {}
    for t in ('graph', 'csv', 'events'):
        for env in ('E0', 'E1'):
            for loc in ('L2', 'L3'):
                def rate(c):
                    rs = [r for r in rows if r['cond'] == c and r['task'] == t and r['env'] == env and r['loc'] == loc]
                    return sum(r['score'] for r in rs) / len(rs) if rs else None
                ra, rb = rate(a), rate(b)
                out[f'{t}|{env}|{loc}'] = None if ra is None or rb is None else round((ra - rb) * 100, 1)
    return out


def main():
    result = {'design': 'W8 ablation: C2 minus location hint = C (remove-one-element), plus repeat reliability',
              'runs': {}, 'contrasts_pp': {}, 'notes': []}
    for name, path in RUNS.items():
        rows = [json.loads(l) for l in path.open()]
        result['runs'][name] = {'trials': len(rows), 'conditions': [summarize(rows, c) for c in CONDS]}
        result['contrasts_pp'][name] = {
            'C2_minus_B': contrast(rows, 'C2', 'B'),
            'C_minus_B (ablation: instruction only)': contrast(rows, 'C', 'B'),
            'C2_minus_C (location hint alone)': contrast(rows, 'C2', 'C'),
            'A_minus_B (no skill vs skill)': contrast(rows, 'A', 'B'),
        }
        result.setdefault('cell_diffs_pp', {})[name] = {
            'C2_minus_B': cell_diffs(rows, 'C2', 'B'),
            'C_minus_B': cell_diffs(rows, 'C', 'B'),
            'C2_minus_C': cell_diffs(rows, 'C2', 'C'),
        }
    result['notes'] = [
        'main-002 repeats all share input_seed 20261020 (legacy design); repeats vary only model sampling.',
        'cost_usd uses list price upper bound (no cache discount), as recorded in trials_all.jsonl.',
        'Contrasts are descriptive; 3 task families x 1 model, so no population inference.',
        'pass^3 uses repeats 1-3 declared here, not chosen after seeing results.',
    ]
    out = EXP / 'analysis/w8_ablation.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    main()
