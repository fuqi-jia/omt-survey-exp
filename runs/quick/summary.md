# Experiment summary: quick

- Total runs: 74
- Solvers: $\nu$Z (OMT), OptiMathSAT (OMT), CBC (MILP), HiGHS (MILP), SCIP (MILP), Gecode (CP), CP-SAT (CP)
- Instances: 12

## Proved optimal per category

| Category | $\nu$Z | OptiMathSAT | CBC | HiGHS | SCIP | Gecode | CP-SAT |
|---|---|---|---|---|---|---|---|
| A | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| B | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| C | 2/2 | 2/2 | -- | -- | -- | -- | -- |

## Notes

- Median solve time and solved/total tables: see `tables/`.
- Per-family scaling curves and anytime trajectory: see `figures/`.
- Anytime example instance: `A_knapsack_10_0`.
