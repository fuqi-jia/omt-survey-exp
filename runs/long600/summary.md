# Experiment summary: long600

- Total runs: 801
- Solvers: $\nu$Z (OMT), OptiMathSAT (OMT), CBC (MILP), HiGHS (MILP), SCIP (MILP), CBC(bigM) (MILP), HiGHS(bigM) (MILP), SCIP(bigM) (MILP), HiGHS(hull) (MILP), Gurobi(ind) (MILP), CPLEX(ind) (MILP), Gecode (CP), CP-SAT (CP)
- Instances: 81

## Proved optimal per category

| Category | $\nu$Z | OptiMathSAT | CBC | HiGHS | SCIP | CBC(bigM) | HiGHS(bigM) | SCIP(bigM) | HiGHS(hull) | Gurobi(ind) | CPLEX(ind) | Gecode | CP-SAT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 23/27 | 20/27 | 27/27 | 27/27 | 27/27 | -- | -- | -- | -- | 27/27 | 27/27 | 3/27 | 27/27 |
| B | 47/54 | 47/54 | 30/30 | 30/30 | 30/30 | 23/24 | 22/24 | 21/24 | 18/24 | 54/54 | 54/54 | 37/54 | 54/54 |

## Notes

- Median solve time and solved/total tables: see `tables/`.
- Per-family scaling curves and anytime trajectory: see `figures/`.
- Anytime example instance: `A_knapsack_640_1`.
