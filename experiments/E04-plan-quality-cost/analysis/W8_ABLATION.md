# W8 ablation — role diversity in the low-cost planner ensemble

The completed focused run compares E (role-diverse candidates) with C (the same number of homogeneous candidates). Both use the same low-cost model, task, synthesis prompt, output limits, and judge. Only candidate role instructions differ.

## Results

| Condition | Mean plan score /100 | Pass rate (n) | Repeat SD (pp) | pass^3 | Tokens / sample | Total estimated cost | Cost per passing plan |
|---|---:|---:|---:|---:|---:|---:|---:|
| C — role specialization removed | 85.47 | 89.58% (43/48) | 3.61 | 13/16 | 30015 | $0.824763 | $0.01918 |
| E — role-diverse intervention | 85.10 | 89.58% (43/48) | 13.01 | 12/16 | 32702 | $0.881982 | $0.02051 |

E − C paired mean score difference: -0.36 points; 95% task-cluster bootstrap CI [-3.26, +2.66].
E − C pass-rate difference: +0.00 percentage points; task-cluster bootstrap 95% CI [-10.42, +12.50].
Score wins by task (E / C / tie): 7 / 9 / 0.
Known spend across both conditions: $1.706745; unknown-cost calls: 0.

## Interpretation

Treat this as an exploratory ablation. The paired interval is task-clustered; the sample contains 16 tasks and three repeats per condition. It measures plan quality and estimated API cost, not task execution success or equal-dollar-budget performance.

Repeat SD is the sample standard deviation of the three repeat-level success rates. pass^3 is the number of tasks that passed in all three repeats. Cost per passing plan includes generation and judge calls.

## Reproduction

The source records, invocation, manifest, case snapshot, samples.csv, summary.md, and summary.json are stored in `results/followup-20261125-role-ablation/`. The exact runner and dependency source snapshot is in that result folder's `source/` directory. Recompute the analysis offline with:

```powershell
uv run --python 3.11 python analysis/analyze_ablation.py results/followup-20261125-role-ablation
```

The completed run ID is `real_ablation_C_E_20261124T155858_688389Z` (2026-11-25 KST); it took about 3 hours 11 minutes. Two earlier starts before the environment key was refreshed stopped after three HTTP 401 candidate calls each. Those six calls are excluded from this run's totals; their billing status is unknown. The completed 96-sample run itself had zero errors and zero unknown-cost calls.
