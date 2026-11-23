"""Runner and offline replay validator for E05 — Memory Applicability Judgment.

Usage (from repository root):
  # 1. Offline replay from saved raw outputs into a new run-id directory:
  python3 experiments/E05-memory-applicability/src/run.py --run-id verify-001 --stage span-tradeoff

  # 2. Validate with official AgentProof harness:
  python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/verify-001
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

EXPERIMENT = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from summarize import summarize


STAGE_MAP = {
    'comparative': (
        'results/raw/holdout_n159_d0_d2_d4_d5.json',
        'D2', 'D5',
        'D2_Structured_FactualConsistency_Audit',
        'D5_Conservative_Comparative_Applicability'
    ),
    'span-tradeoff': (
        'results/raw/d6_g_t_onset_ablation.json',
        'D5', 'D6_G',
        'D5_Conservative_Comparative_Applicability',
        'D6G_Span_Structure_Comparative_Applicability'
    ),
}


def write_json(path: Path, value: dict):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='New directory name under results/pilot/; never overwrites')
    parser.add_argument('--stage', choices=list(STAGE_MAP.keys()), default='span-tradeoff',
                        help='Which pilot stage comparison to package (default: span-tradeoff)')
    args = parser.parse_args()

    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('run-id must contain only letters, numbers, underscores or hyphens')

    out_dir = EXPERIMENT / 'results/pilot' / args.run_id
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f'run-id {args.run_id} already exists; choose a new run-id')

    task_file = EXPERIMENT / 'data/tasks.json'
    tasks = json.loads(task_file.read_text(encoding='utf-8'))
    task_by_id = {t['task_id']: t for t in tasks}
    data_sha256 = hashlib.sha256(task_file.read_bytes()).hexdigest()

    configs = {
        c: json.loads((EXPERIMENT / f'configs/{c}.json').read_text(encoding='utf-8'))
        for c in ('baseline', 'intervention')
    }

    raw_rel, base_key, intv_key, base_label, intv_label = STAGE_MAP[args.stage]
    raw_blob = json.loads((EXPERIMENT / raw_rel).read_text(encoding='utf-8'))
    if 'holdout_n159' in raw_blob:
        raw_results = raw_blob['holdout_n159']['raw_results']
    else:
        raw_results = raw_blob['raw_results']

    base_records = raw_results[base_key]
    intv_records = raw_results[intv_key]
    task_ids = list(base_records.keys())

    manifest = {
        'experiment_id': EXPERIMENT.name,
        'run_id': args.run_id,
        'execution_mode': 'real',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'code_commit': 'HEAD',
        'code_dirty': True,
        'model': 'google/gemma-4-31b-it',
        'configs': {
            'baseline': {**configs['baseline'], 'label': base_label},
            'intervention': {**configs['intervention'], 'label': intv_label},
        },
        'task_ids': task_ids,
        'data_sha256': data_sha256,
        'repeats_per_condition': {'baseline': 1, 'intervention': 1},
        'execution_order': 'standalone single-prompt per condition and task; temperature=0.0',
        'seed_policy': 'seed=42 for goal-disjoint data split and TF-IDF retrieval; temperature=0.0',
        'cost_basis': 'OpenRouter google/gemma-4-31b-it API call; replayed from saved raw outputs',
        'latency_basis': 'not measured in cached batch evaluation',
        'environment': {'python': sys.version, 'dependencies': 'Python standard library'},
    }
    write_json(out_dir / 'manifest.json', manifest)

    missing_reasons = {
        'latency_ms': 'cached OpenRouter API response; per-trial wall-clock latency not separately recorded',
        'input_tokens': 'OpenRouter response text cached without per-call usage object',
        'output_tokens': 'OpenRouter response text cached without per-call usage object',
        'cost_usd': 'OpenRouter account-level spend tracked (~$5.03 total across all pilot stages); per-trial cost not split'
    }

    lines = []
    for cond_name, records, cond_label in [('baseline', base_records, base_label), ('intervention', intv_records, intv_label)]:
        for tid in task_ids:
            rec = records[tid]
            t_info = task_by_id[tid]
            gt_set = set(t_info['gt_types'])
            pred = rec.get('pred_type', '')
            ok = bool(pred in gt_set)
            row = {
                'run_id': args.run_id,
                'task_id': tid,
                'condition': cond_name,
                'repeat_id': 1,
                'status': 'success' if ok else 'failure',
                'score': 1 if ok else 0,
                'latency_ms': None,
                'input_tokens': None,
                'output_tokens': None,
                'cost_usd': None,
                'missing_reasons': missing_reasons,
                'evidence': {
                    'config': f'configs/{cond_name}.json',
                    'condition_label': cond_label,
                    'goal': t_info['goal'],
                    'target_range': t_info['where'],
                    'expected_gt_types': t_info['gt_types'],
                    'retrieved_memory_type': t_info['retrieved_memory_type'],
                    'initial_failure_type': rec.get('t_init', ''),
                    'predicted_failure_type': pred,
                    'decision': rec.get('raw_dec', ''),
                    'overridden': bool(rec.get('overridden', False)),
                    'supporting_steps': rec.get('supp_steps', []),
                    'contradicting_steps': rec.get('cont_steps', []),
                    'grader': 'exact taxonomy label membership in ground-truth core_failure types for target step range'
                }
            }
            lines.append(json.dumps(row, ensure_ascii=False, allow_nan=False))

    (out_dir / 'trials.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write_json(out_dir / 'summary.json', summarize(out_dir))
    print(out_dir.relative_to(ROOT))


if __name__ == '__main__':
    main()
