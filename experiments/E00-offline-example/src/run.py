"""Offline fixture exercise. Does not call a model, tool, or external API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

EXPERIMENT = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from summarize import summarize


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='New directory name; existing runs are never overwritten')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('run-id must contain only letters, numbers, underscores or hyphens')
    task_file = EXPERIMENT / 'data/tasks.json'
    tasks = json.loads(task_file.read_text())
    configs = {condition: json.loads((EXPERIMENT / f'configs/{condition}.json').read_text())
               for condition in ('baseline', 'intervention')}
    task_ids = [task['task_id'] for task in tasks]
    if not tasks or len(set(task_ids)) != len(task_ids):
        parser.error('tasks must be nonempty and unique')
    for condition, config in configs.items():
        if config['condition'] != condition or type(config['repeats']) is not int or config['repeats'] < 1:
            parser.error('config must have matching condition and positive integer repeats')
        if set(config['mock_outputs']) != set(task_ids):
            parser.error('mock_outputs must cover exactly the configured tasks')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                         cwd=ROOT, text=True).strip())
    out = EXPERIMENT / 'results/pilot' / args.run_id
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error('run-id already exists; choose a new run-id')
    manifest = {
        'experiment_id': EXPERIMENT.name, 'run_id': args.run_id, 'execution_mode': 'mock',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'code_commit': commit,
        'code_dirty': dirty, 'model': 'mock-fixed-responses-v1', 'configs': configs,
        'task_ids': task_ids, 'data_sha256': hashlib.sha256(task_file.read_bytes()).hexdigest(),
        'repeats_per_condition': {key: cfg['repeats'] for key, cfg in configs.items()},
        'execution_order': 'condition, task, repeat; no retries',
        'seed_policy': 'not applicable: fixed mock responses',
        'cost_basis': 'not measured; no model call; null is not a real-run cost estimate',
        'latency_basis': 'local fixture lookup and exact-match grading only',
        'environment': {'python': sys.version, 'dependencies': 'Python standard library'},
        'warning': 'Fixture exercise only. Not evidence of intervention efficacy.'}
    write_json(out / 'manifest.json', manifest)
    with (out / 'trials.jsonl').open('w') as stream:
        for condition, config in configs.items():
            for task in tasks:
                for repeat in range(1, config['repeats'] + 1):
                    start = perf_counter()
                    answer = config['mock_outputs'][task['task_id']]
                    success = answer.strip() == task['expected'].strip()
                    elapsed = (perf_counter() - start) * 1000
                    row = {
                        'run_id': args.run_id, 'task_id': task['task_id'], 'condition': condition,
                        'repeat_id': repeat, 'status': 'success' if success else 'failure',
                        'score': int(success), 'latency_ms': elapsed, 'input_tokens': None,
                        'output_tokens': None, 'cost_usd': None,
                        'missing_reasons': {key: 'mock run: no model API call' for key in
                                            ('input_tokens', 'output_tokens', 'cost_usd')},
                        'evidence': {'config': f'configs/{condition}.json', 'question': task['question'],
                                     'response': answer, 'expected': task['expected'],
                                     'grader': 'exact string match after strip; no numeric normalization'}}
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    write_json(out / 'summary.json', summarize(out))
    print(out.relative_to(ROOT))


if __name__ == '__main__':
    main()
