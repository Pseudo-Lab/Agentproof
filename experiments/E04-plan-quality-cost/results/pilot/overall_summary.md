# E04 latest-outcome analysis

One latest record per planned task × group × repeat cell. Invalid plans score zero; generation errors are unscored.

| Group | Latest outcomes | Mean Plan score /100 | Pass rate among scored/invalid | Latest known cost |
|---|---:|---:|---:|---:|
| A | 35 graded, 1 invalid, 0 errors | 96.11 | 34/36 (94.4%) | USD 1.784512 |
| B | 33 graded, 0 invalid, 3 errors | 89.70 | 31/33 (93.9%) | USD 0.503455 |
| C | 30 graded, 0 invalid, 6 errors | 90.75 | 30/30 (100.0%) | USD 0.701624 |

## Paired task comparisons

- B-A: 11 complete task pairs; mean difference -6.29; 95% task bootstrap interval [-12.50, 1.89]. The 5-point noninferiority criterion was not met.
- C-A: 11 complete task pairs; mean difference -5.74; 95% task bootstrap interval [-12.22, 3.30]. The 5-point noninferiority criterion was not met.

## Cost and retry history

The source ledger contains 182 attempts for 108 planned cells. Known token-based spend is USD 3.052875, with 114 unknown-cost calls; this is a lower bound, not a provider invoice.

## Interpretation

C is 1.05 points above B on mean Plan score and about 39% more expensive on the latest outcome rows. Neither B nor C establishes noninferiority to A. Nine latest cells were generation errors (3 B, 6 C); the records show outputs truncated at the 6,000 completion-token cap. This run measured plan quality, not task execution success.

Promptfoo ran the groups and invoked a custom Python assertion. A deterministic JSON Plan contract check ran first; the shared gpt-6.1-sol judge then scored coverage (30), feasibility (25), dependencies (20), verification (15), and recovery (10). Passing required score ≥75 and no critical error.

The source archive includes final Plan outputs, judge evidence, C candidate Plans, model-call stages, and a compact attempt history. Provider response IDs and secrets are omitted. Evaluation references are included only post-run; generation did not receive them.
