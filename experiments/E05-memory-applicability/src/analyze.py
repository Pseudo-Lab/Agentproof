"""Reproduce all tables and Beneficial/Harmful Override metrics reported in CARD.md (no API key needed)."""
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')
EXPERIMENT = Path(__file__).resolve().parents[1]
RAW = EXPERIMENT / 'results/raw'
TASKS = json.loads((EXPERIMENT / 'data/tasks.json').read_text(encoding='utf-8'))
GT_BY_ID = {t['task_id']: set(t['gt_types']) for t in TASKS}


def compute_override_stats(records: dict) -> dict:
    total = len(records)
    init_ok_cnt = 0
    final_ok_cnt = 0
    ben_override = 0  # init wrong -> final right
    harm_override = 0  # init right -> final wrong
    for tid, r in records.items():
        gt = GT_BY_ID[tid]
        init_ok = r.get('t_init', '') in gt
        fin_ok = r.get('pred_type', '') in gt
        init_ok_cnt += int(init_ok)
        final_ok_cnt += int(fin_ok)
        if not init_ok and fin_ok:
            ben_override += 1
        elif init_ok and not fin_ok:
            harm_override += 1
    return {
        'N': total,
        'acc': final_ok_cnt / total * 100,
        'final_ok': final_ok_cnt,
        'beneficial_override': ben_override,
        'harmful_override': harm_override,
    }


def main():
    print('=== 1. Stage 1 Initial Baseline (Test N=100) ===')
    print((RAW / 'initial_test_n100_summary.csv').read_text(encoding='utf-8').strip())

    print('\n=== 2. Stage 2 Input Position x Evidence Structure (Test N=100) ===')
    fact = json.load((RAW / 'factorial_d0_d3_ablation.json').open(encoding='utf-8'))
    for k, label in [
        ('D0', 'Trajectory-First + Simple Array (D0)'),
        ('D1', 'Memory-First     + Simple Array (D1)'),
        ('D2', 'Trajectory-First + Structured   (D2)'),
        ('D3', 'Memory-First     + Structured   (D3)'),
    ]:
        st = compute_override_stats(fact['test_show0']['raw_results'][k])
        print(f"  {label:38s}: Acc={st['acc']:5.1f}% ({st['final_ok']}/{st['N']}) | Beneficial(W->C)={st['beneficial_override']:2d} | Harmful(C->W)={st['harmful_override']:2d}")

    print('\n=== 3. Stage 3 & 4 Acceptance-Rejection Trade-off (Eval N=159) ===')
    hold = json.load((RAW / 'holdout_n159_d0_d2_d4_d5.json').open(encoding='utf-8'))
    d6 = json.load((RAW / 'd6_g_t_onset_ablation.json').open(encoding='utf-8'))
    a_ok = sum(1 for tid, r in hold['raw_results']['A'].items() if (r if isinstance(r, str) else r.get('pred_type')) in GT_BY_ID[tid])
    print(f"  {'No Memory (Reference A)':38s}: Acc={a_ok/159*100:5.1f}% ({a_ok}/159)")
    for k, src, label in [
        ('D0', hold['raw_results'], 'Simple Evidence Array (D0)'),
        ('D2', hold['raw_results'], 'Structured Bilateral Evidence (D2)'),
        ('D5', hold['raw_results'], 'Conservative Comparative Review (D5)'),
        ('D6_G', d6['holdout_n159']['raw_results'], 'Span-Structure Enhanced Review (D6-G)'),
        ('Onset_D', d6['holdout_n159']['raw_results'], 'Onset + Search-Label Restriction (Aux)'),
    ]:
        st = compute_override_stats(src[k])
        print(f"  {label:38s}: Acc={st['acc']:5.1f}% ({st['final_ok']}/{st['N']}) | Beneficial(W->C)={st['beneficial_override']:2d} | Harmful(C->W)={st['harmful_override']:2d}")


if __name__ == '__main__':
    main()
