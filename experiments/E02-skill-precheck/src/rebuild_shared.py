"""Rebuild the shared-schema files of an existing E02 run from trials_all.jsonl. Offline, no API.

The shared AgentProof record must carry the pre-registered primary intervention (C2 = pre-check
+ evidence-location hint, P1 in CARD.md). Earlier runs wrote C (pre-check without the hint) as
"intervention" because COND_TO_SHARED was not updated for v3. This script corrects that:

  trials.jsonl              B (baseline) vs C2 (intervention), shared schema
  trials_ablation_C.jsonl   C arm (pre-check without location hint), shared schema, label C
  summary.json              shared harness summary of trials.jsonl (only if summarize accepts it)

Usage: python3 src/rebuild_shared.py results/main/main-002 [more run folders ...]
The row construction mirrors run.py; B rows are checked against the existing trials.jsonl when present.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'harness'))  # repo-level shared summarizer
from summarize import summarize  # noqa: E402

PRIMARY = {'B': 'baseline', 'C2': 'intervention'}


def shared_row(r, label, shared_condition):
    return {
        'run_id': r['run_id'], 'task_id': r['task_id'], 'condition': shared_condition,
        'repeat_id': r['repeat_id'], 'status': r['status'], 'score': r['score'],
        'latency_ms': r['latency_ms'], 'input_tokens': r['input_tokens'], 'output_tokens': r['output_tokens'],
        'cost_usd': r['cost_usd'], 'missing_reasons': {},
        'evidence': {'trace': r['trace'], 'grade_reason': r['grade_reason'], 'stop_reason': r['stop_reason'],
                     'hook_count': r['hook_count'], 'label': label},
    }


def rebuild(folder):
    folder = Path(folder)
    rows = [json.loads(line) for line in (folder / 'trials_all.jsonl').read_text().splitlines() if line.strip()]
    primary = [shared_row(r, r['cond'], PRIMARY[r['cond']]) for r in rows if r['cond'] in PRIMARY]
    ablation = [shared_row(r, 'C', 'intervention') for r in rows if r['cond'] == 'C']

    old = folder / 'trials.jsonl'
    if old.exists():
        old_b = [json.loads(line) for line in old.read_text().splitlines() if line.strip()]
        old_b = [r for r in old_b if r['evidence'].get('label') == 'B']
        new_b = [r for r in primary if r['evidence']['label'] == 'B']
        if old_b != new_b:
            raise SystemExit(f'{folder}: rebuilt baseline rows differ from existing trials.jsonl; stop')

    (folder / 'trials.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in primary))
    if ablation:
        (folder / 'trials_ablation_C.jsonl').write_text(
            ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in ablation))
    try:
        summary = summarize(folder)
    except ValueError as exc:  # partial designs (e.g. single-seed checks) do not fit the shared summarizer
        summary = {'not_summarized': str(exc)}
    (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(folder, 'primary rows', len(primary), 'ablation C rows', len(ablation), 'summary keys', list(summary))


if __name__ == '__main__':
    for path in sys.argv[1:]:
        rebuild(ROOT / path if not Path(path).is_absolute() else path)
