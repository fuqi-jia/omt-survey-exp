# Experiment summary: enc

- Total runs: 54
- Solvers: $\nu$Z (OMT), OptiMathSAT (OMT), CBC(bigM) (MILP), HiGHS(bigM) (MILP), SCIP(bigM) (MILP), HiGHS(hull) (MILP), Gurobi(ind) (MILP), CPLEX(ind) (MILP), Gecode (CP), CP-SAT (CP)
- Instances: 7

## Proved optimal per category

| Category | $\nu$Z | OptiMathSAT | CBC(bigM) | HiGHS(bigM) | SCIP(bigM) | HiGHS(hull) | Gurobi(ind) | CPLEX(ind) | Gecode | CP-SAT |
|---|---|---|---|---|---|---|---|---|---|---|
| B | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| C | 3/3 | 3/3 | -- | -- | -- | -- | -- | -- | -- | -- |

## Notes

- Median solve time and solved/total tables: see `tables/`.
- Per-family scaling curves and anytime trajectory: see `figures/`.
- Anytime example instance: `B_jobshop_5_0`.
