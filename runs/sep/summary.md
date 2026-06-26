# Experiment summary: sep

- Total runs: 102
- Solvers: $\nu$Z (OMT), OptiMathSAT (OMT), CBC (MILP), HiGHS (MILP), SCIP (MILP), CBC(bigM) (MILP), HiGHS(bigM) (MILP), SCIP(bigM) (MILP), HiGHS(hull) (MILP), Gurobi(ind) (MILP), CPLEX(ind) (MILP), Gecode (CP), CP-SAT (CP)
- Instances: 11

## Proved optimal per category

| Category | $\nu$Z | OptiMathSAT | CBC | HiGHS | SCIP | CBC(bigM) | HiGHS(bigM) | SCIP(bigM) | HiGHS(hull) | Gurobi(ind) | CPLEX(ind) | Gecode | CP-SAT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3/5 | 0/5 | 5/5 | 5/5 | 5/5 | -- | -- | -- | -- | 3/5 | 2/5 | 0/5 | 5/5 |
| B | 3/6 | 4/6 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 2/3 | 0/3 | 6/6 | 5/6 | 2/6 | 5/6 |

## Notes

- Median solve time and solved/total tables: see `tables/`.
- Per-family scaling curves and anytime trajectory: see `figures/`.
- Anytime example instance: `A_knapsack_640_0`.
