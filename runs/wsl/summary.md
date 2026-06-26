# Experiment summary: wsl

- Total runs: 465
- Solvers: $\nu$Z (OMT), OptiMathSAT (OMT), CBC (MILP), HiGHS (MILP), SCIP (MILP), Gecode (CP), CP-SAT (CP)
- Instances: 75

## Proved optimal per category

| Category | $\nu$Z | OptiMathSAT | CBC | HiGHS | SCIP | Gecode | CP-SAT |
|---|---|---|---|---|---|---|---|
| A | 24/24 | 22/24 | 24/24 | 24/24 | 24/24 | 19/24 | 24/24 |
| B | 39/39 | 39/39 | 39/39 | 39/39 | 39/39 | 39/39 | 39/39 |
| C | 12/12 | 12/12 | -- | -- | -- | -- | -- |

## Notes

- Median solve time and solved/total tables: see `tables/`.
- Per-family scaling curves and anytime trajectory: see `figures/`.
- Anytime example instance: `A_knapsack_40_2`.
