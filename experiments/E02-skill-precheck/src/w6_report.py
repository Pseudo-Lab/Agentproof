"""Offline W6 evidence export. Never calls a model or changes experiment data.

python3 src/w6_report.py
Errors count as non-success in all primary denominators. Task-bootstrap intervals
are descriptive, with only 3 or 6 task clusters; they are not a new confirmation test.
"""
import json
import random
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]


def validate_rows(rows):
    ids = [r['trial_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate trial_id')


def summarize_rows(rows):
    return dict(success=sum(r['status'] == 'success' for r in rows), n=len(rows),
                errors=sum(r['status'] == 'error' for r in rows),
                cost_usd=round(sum(r.get('cost_usd', 0) for r in rows), 6))


def cluster_difference(rows, a, b, seed=20261109):
    diffs = {}
    for task in sorted({r['task'] for r in rows}):
        arms = [[r for r in rows if r['task'] == task and r['cond'] == c] for c in (a, b)]
        if any(not arm for arm in arms):
            raise ValueError(f'missing comparison arm: {task}')
        rates = [sum(r['status'] == 'success' for r in arm) / len(arm) for arm in arms]
        diffs[task] = (rates[0] - rates[1]) * 100
    if not diffs:
        raise ValueError('no tasks')
    values = list(diffs.values())
    rng = random.Random(seed)
    draws = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(10000))
    return dict(diff_pp=round(sum(values) / len(values), 2),
                ci95_pp=[round(draws[249], 2), round(draws[9749], 2)],
                per_task_pp={t: round(v, 2) for t, v in diffs.items()})


def load_run(relative):
    folder = EXPERIMENT / relative
    manifest = json.loads((folder / 'manifest.json').read_text())
    source = folder / 'trials_all.jsonl'
    if not source.exists():
        source = folder / 'trials.jsonl'
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    validate_rows(rows)
    return manifest, rows


def main():
    runs = {
        'v3_original': 'results/main/main-002',
        'v4_original': 'results/sb/main/main-sb-mini-001',
        'v3_replication': 'results/replication/w6-v3-20261109',
        'v4_replication': 'results/sb/replication/w6-sb-20261109b',
    }
    result = {'policy': 'All executed trials included; API and infrastructure errors are non-success. '
                       'Runs are reported separately. Bootstrap resamples tasks, 10000 draws, seed 20261109. '
                       'Intervals and new comparisons are exploratory; not final-design H1.', 'runs': {}}
    for name, relative in runs.items():
        manifest, rows = load_run(relative)
        cells = {}
        for r in rows:
            key = '/'.join([r['task'], r['env'], r.get('loc', 'native'), r['cond']])
            cells.setdefault(key, []).append(r)
        selected = [r for r in rows if r['env'] == 'E1' and
                    (name.startswith('v4') or r['loc'] == 'L3')]
        comparisons = {'C2-B': cluster_difference(selected, 'C2', 'B')}
        if name.startswith('v4'):
            comparisons['P-C2'] = cluster_difference(selected, 'P', 'C2')
        result['runs'][name] = dict(
            path=relative, model=manifest['model'], plan=manifest['plan'],
            completed=len(rows), planned=manifest.get('planned_trials'),
            total=summarize_rows(rows),
            by_condition={c: summarize_rows([r for r in rows if r['cond'] == c])
                          for c in sorted({r['cond'] for r in rows})},
            cells={key: summarize_rows(rs) for key, rs in cells.items()},
            comparisons=comparisons,
            mechanism={c: dict(n=len(rs := [r for r in selected if r['cond'] == c]),
                               opened=sum(r.get('evidence_opened', False) for r in rs),
                               success_opened=sum(r['status'] == 'success' and r.get('evidence_opened', False) for r in rs))
                       for c in sorted({r['cond'] for r in selected})})
    result['new_cost_usd'] = round(sum(result['runs'][name]['total']['cost_usd']
                                     for name in ('v3_replication', 'v4_replication')), 6)
    out = EXPERIMENT / 'presentation/w6/evidence.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    main()
