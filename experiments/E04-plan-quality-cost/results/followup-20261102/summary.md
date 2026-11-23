# Plan benchmark

Latest planned cells: 240 / 240; recorded attempt records: 240. All costs are USD estimates.

| Group | Latest outcomes | Scored | Plan /100 | Pass rate | All attempt records | Generation $ | Judge $ | Total known $ | Unknown-cost calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 48 | 48 | 94.09 | 0.94 | 48 | 1.708415 | 0.363240 | 2.071655 | 0 |
| B | 48 | 48 | 77.66 | 0.67 | 48 | 0.097640 | 0.340370 | 0.438010 | 0 |
| C | 48 | 48 | 84.30 | 0.90 | 48 | 0.465573 | 0.344517 | 0.810089 | 0 |
| D | 48 | 48 | 83.83 | 0.75 | 48 | 0.699652 | 0.364549 | 1.064201 | 0 |
| E | 48 | 48 | 84.30 | 0.81 | 48 | 0.505100 | 0.361405 | 0.866505 | 0 |

All groups combined known spend across 240 recorded sample attempts: $5.250461; unknown-cost calls: 0.

- A: latest generation errors=0 (all attempts=0); latest judge errors=0 (all attempts=0); invalid plans=0; judge critical-error rate=0.06; mean generation cost=$0.035592.
- B: latest generation errors=0 (all attempts=0); latest judge errors=0 (all attempts=0); invalid plans=1; judge critical-error rate=0.09; mean generation cost=$0.002034.
- C: latest generation errors=0 (all attempts=0); latest judge errors=0 (all attempts=0); invalid plans=0; judge critical-error rate=0.04; mean generation cost=$0.009699.
- D: latest generation errors=0 (all attempts=0); latest judge errors=0 (all attempts=0); invalid plans=0; judge critical-error rate=0.08; mean generation cost=$0.014576.
- E: latest generation errors=0 (all attempts=0); latest judge errors=0 (all attempts=0); invalid plans=0; judge critical-error rate=0.08; mean generation cost=$0.010523.

Cost per sample, individual plans, grader evidence, errors and call details are in samples.csv and records/.
Unknown-cost calls make displayed spend a lower bound; a timeout may still have been billed.
Generation errors and judge failures are counted separately and excluded from mean quality.
Invalid plan contracts score zero; critical semantic errors also fail even if the score is high.

## Paired comparisons

- B-A: task pairs=16; delta=-16.43; 95% task-cluster bootstrap CI=[-21.822916666666668, -11.40625]; margin=5 points.
- C-A: task pairs=16; delta=-9.79; 95% task-cluster bootstrap CI=[-12.838541666666666, -6.770833333333335]; margin=5 points.
- D-A: task pairs=16; delta=-10.26; 95% task-cluster bootstrap CI=[-14.27083333333333, -6.562499999999997]; margin=5 points.
- E-A: task pairs=16; delta=-9.79; 95% task-cluster bootstrap CI=[-12.916666666666668, -6.770833333333334]; margin=5 points.

## Task layers

| Layer | Group | Latest outcomes / expected | All attempt records | Scored | Plan /100 | Pass rate | Generation $ | Judge $ | Unknown-cost calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | A | 18 / 18 | 18 | 18 | 97.15 | 1.00 | 0.579826 | 0.115004 | 0 |
| baseline | B | 18 / 18 | 18 | 18 | 81.67 | 0.83 | 0.030750 | 0.109945 | 0 |
| baseline | C | 18 / 18 | 18 | 18 | 83.68 | 0.89 | 0.156656 | 0.111546 | 0 |
| baseline | D | 18 / 18 | 18 | 18 | 86.39 | 0.89 | 0.236772 | 0.114739 | 0 |
| baseline | E | 18 / 18 | 18 | 18 | 88.54 | 0.94 | 0.172583 | 0.118272 | 0 |
| challenge | A | 12 / 12 | 12 | 12 | 91.77 | 0.92 | 0.368340 | 0.080491 | 0 |
| challenge | B | 12 / 12 | 12 | 12 | 79.79 | 0.67 | 0.017626 | 0.078551 | 0 |
| challenge | C | 12 / 12 | 12 | 12 | 83.12 | 0.83 | 0.087380 | 0.077980 | 0 |
| challenge | D | 12 / 12 | 12 | 12 | 85.52 | 0.92 | 0.131986 | 0.081563 | 0 |
| challenge | E | 12 / 12 | 12 | 12 | 82.50 | 0.83 | 0.098452 | 0.078251 | 0 |
| coupled_sources | A | 6 / 6 | 6 | 6 | 88.54 | 0.83 | 0.264384 | 0.059855 | 0 |
| coupled_sources | B | 6 / 6 | 6 | 6 | 82.50 | 0.50 | 0.018520 | 0.055062 | 0 |
| coupled_sources | C | 6 / 6 | 6 | 6 | 87.29 | 1.00 | 0.079548 | 0.053554 | 0 |
| coupled_sources | D | 6 / 6 | 6 | 6 | 85.62 | 0.50 | 0.121678 | 0.059515 | 0 |
| coupled_sources | E | 6 / 6 | 6 | 6 | 82.92 | 0.67 | 0.083966 | 0.060214 | 0 |
| independent_sources | A | 6 / 6 | 6 | 6 | 94.79 | 0.83 | 0.261917 | 0.056800 | 0 |
| independent_sources | B | 6 / 6 | 6 | 6 | 59.79 | 0.33 | 0.015053 | 0.047699 | 0 |
| independent_sources | C | 6 / 6 | 6 | 6 | 86.25 | 0.83 | 0.068793 | 0.051535 | 0 |
| independent_sources | D | 6 / 6 | 6 | 6 | 80.00 | 0.50 | 0.102972 | 0.054619 | 0 |
| independent_sources | E | 6 / 6 | 6 | 6 | 84.38 | 0.67 | 0.072433 | 0.054713 | 0 |
| short_constraints | A | 6 / 6 | 6 | 6 | 94.38 | 1.00 | 0.233948 | 0.051089 | 0 |
| short_constraints | B | 6 / 6 | 6 | 6 | 74.38 | 0.67 | 0.015692 | 0.049113 | 0 |
| short_constraints | C | 6 / 6 | 6 | 6 | 83.54 | 1.00 | 0.073196 | 0.049901 | 0 |
| short_constraints | D | 6 / 6 | 6 | 6 | 74.79 | 0.50 | 0.106244 | 0.054112 | 0 |
| short_constraints | E | 6 / 6 | 6 | 6 | 76.46 | 0.67 | 0.077667 | 0.049955 | 0 |
- baseline, B-A: task pairs=6; delta=-15.49; 95% CI=[-20.902777777777782, -10.27777777777778].
- baseline, C-A: task pairs=6; delta=-13.47; 95% CI=[-17.36111111111111, -10.555555555555557].
- baseline, D-A: task pairs=6; delta=-10.76; 95% CI=[-15.555555555555557, -6.25].
- baseline, E-A: task pairs=6; delta=-8.61; 95% CI=[-11.388888888888891, -6.527777777777776].
- challenge, B-A: task pairs=4; delta=-11.98; 95% CI=[-21.041666666666657, -5.208333333333329].
- challenge, C-A: task pairs=4; delta=-8.65; 95% CI=[-15.833333333333329, -1.4583333333333357].
- challenge, D-A: task pairs=4; delta=-6.25; 95% CI=[-11.874999999999993, -0.625].
- challenge, E-A: task pairs=4; delta=-9.27; 95% CI=[-16.666666666666664, -1.875].
- coupled_sources, B-A: task pairs=2; delta=-6.04; 95% CI=[-8.75, -3.3333333333333286].
- coupled_sources, C-A: task pairs=2; delta=-1.25; 95% CI=[-1.25, -1.25].
- coupled_sources, D-A: task pairs=2; delta=-2.92; 95% CI=[-3.75, -2.0833333333333286].
- coupled_sources, E-A: task pairs=2; delta=-5.62; 95% CI=[-6.666666666666657, -4.583333333333329].
- independent_sources, B-A: task pairs=2; delta=-35.00; 95% CI=[-40.833333333333336, -29.166666666666664].
- independent_sources, C-A: task pairs=2; delta=-8.54; 95% CI=[-13.333333333333329, -3.75].
- independent_sources, D-A: task pairs=2; delta=-14.79; 95% CI=[-24.166666666666657, -5.416666666666671].
- independent_sources, E-A: task pairs=2; delta=-10.42; 95% CI=[-19.58333333333333, -1.25].
- short_constraints, B-A: task pairs=2; delta=-20.00; 95% CI=[-29.58333333333333, -10.416666666666671].
- short_constraints, C-A: task pairs=2; delta=-10.83; 95% CI=[-12.916666666666671, -8.75].
- short_constraints, D-A: task pairs=2; delta=-19.58; 95% CI=[-25.83333333333333, -13.333333333333329].
- short_constraints, E-A: task pairs=2; delta=-17.92; 95% CI=[-19.16666666666667, -16.66666666666667].

These intervals are exploratory. Example tasks and small layer subsets are pilot data, not evidence of equivalence.
A quality noninferiority signal alone does not establish cheaper or equally reliable performance.
Review missing/error rates, critical errors, and generation cost before concluding. Human evaluation is not part of this run.
This run measures achieved quality and cost, not equal-dollar-budget performance.
