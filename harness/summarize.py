"""Validate and summarize complete, single-attempt baseline/intervention runs (offline)."""
import argparse
import json
import math
from pathlib import Path

CONDITIONS = ('baseline', 'intervention')
METRICS = ('latency_ms', 'input_tokens', 'output_tokens', 'cost_usd')


def summarize(run_dir):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    rows = [json.loads(line) for line in (run_dir / 'trials.jsonl').read_text().splitlines() if line.strip()]
    if manifest.get('execution_mode') not in ('mock', 'real'):
        raise ValueError('manifest.execution_mode must be mock or real')
    tasks = manifest['task_ids']
    repeats = manifest['repeats_per_condition']
    if not tasks or len(set(tasks)) != len(tasks):
        raise ValueError('task_ids must be nonempty and unique')
    if set(repeats) != set(CONDITIONS) or any(type(n) is not int or n < 1 for n in repeats.values()):
        raise ValueError('repeats_per_condition must specify positive integers for both conditions')
    expected = {(condition, task, repeat) for condition in CONDITIONS for task in tasks
                for repeat in range(1, repeats[condition] + 1)}
    seen = set()
    for row in rows:
        for field in ('run_id', 'task_id', 'condition', 'repeat_id', 'status', 'score', *METRICS,
                      'missing_reasons', 'evidence'):
            if field not in row:
                raise ValueError(f'missing trial field: {field}')
        if row['run_id'] != manifest['run_id']:
            raise ValueError('trial run_id differs from manifest')
        if type(row['repeat_id']) is not int:
            raise ValueError('repeat_id must be an integer')
        key = (row['condition'], row['task_id'], row['repeat_id'])
        if key not in expected or key in seen:
            raise ValueError(f'unexpected or duplicate trial: {key}')
        seen.add(key)
        if row['status'] not in ('success', 'failure', 'error', 'timeout'):
            raise ValueError('invalid status')
        if not isinstance(row['evidence'], dict) or not row['evidence']:
            raise ValueError('evidence must be a nonempty object')
        if not isinstance(row['missing_reasons'], dict):
            raise ValueError('missing_reasons must be an object')
        for field in ('score', *METRICS):
            value = row[field]
            if value is None:
                reason = row['missing_reasons'].get(field)
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError(f'null {field} requires a missing reason')
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{field} must be a finite number or null')
            elif field != 'score' and value < 0:
                raise ValueError(f'{field} must be nonnegative')
            elif field in ('input_tokens', 'output_tokens') and type(value) is not int:
                raise ValueError(f'{field} must be an integer')
    if seen != expected:
        raise ValueError(f'incomplete run: {len(expected - seen)} trials missing')
    result = {'run_id': manifest['run_id'], 'execution_mode': manifest['execution_mode'],
              'reliability_definition': 'all_repeats_success_rate', 'conditions': {}}
    for condition in CONDITIONS:
        subset = [row for row in rows if row['condition'] == condition]
        successes = sum(row['status'] == 'success' for row in subset)
        stable = sum(all(row['status'] == 'success' for row in subset if row['task_id'] == task)
                     for task in tasks)
        metrics = {}
        for field in METRICS:
            values = [row[field] for row in subset if row[field] is not None]
            metrics[field] = {'measured_trials': len(values),
                              'total': sum(values) if len(values) == len(subset) else None}
        result['conditions'][condition] = {
            'tasks': len(tasks), 'repeats_per_task': repeats[condition], 'trials': len(subset),
            'successes': successes, 'success_rate': successes / len(subset),
            'all_repeats_success_tasks': stable, 'all_repeats_success_rate': stable / len(tasks),
            'errors': sum(row['status'] == 'error' for row in subset),
            'timeouts': sum(row['status'] == 'timeout' for row in subset), 'metrics': metrics}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(summarize(args.run_dir), ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f'Invalid run: {exc}\n')


if __name__ == '__main__':
    main()
