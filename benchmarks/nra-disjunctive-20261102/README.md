# Coupled disjunctive nonlinear resource allocation

Nine generated instances: `n=4,8,12`, seeds `0,1,2`. Each unit has production
`x_i` and cost `z_i`, bounded by `0<=x_i<=u_i` and `0<=z_i<=M_i`, with
`M_i=s_i+a_i*u_i^2`. The model minimizes total cost under a shared demand:

```text
sum(b_i*x_i) >= D
AND_i [ (x_i=0 AND z_i=0) OR (x_i>=l_i AND z_i>=s_i+a_i*x_i^2) ]
```

Parameter ranges and RNG seeds are archived in `protocol.json`. Demand is 45%
of total weighted capacity, rounded down. The demand constraint couples the
unit choices. The disjunctions are part of the feasible set.

The SMT inputs contain the explicit Boolean `or`. Gurobi and Couenne use the
equivalent binary formulation, with `y_i` binary:

```text
l_i*y_i <= x_i <= u_i*y_i
0 <= z_i <= M_i*y_i
z_i >= s_i*y_i + a_i*x_i^2
```

IPOPT and SLSQP are compared on the continuous MINLPLib cohort; they do not
solve this integer/disjunctive cohort.

For each instance, every one of the `2^n` active sets is enumerated. Each
remaining convex quadratic allocation problem has a rational water-filling
solution. The minimum over all sets is archived as an exact fraction, with a
reference vector and active mask. The Gurobi results independently agree with
all nine references at the common feasibility/objective tolerances.

Generator and runner: `scripts/nra_disjunctive_20261102.py`. Authoritative output:
`runs/nra_disjunctive_20261102/`. Each solver call has a 120 s limit, one thread,
and a 4 GB memory limit. Independent witness recovery for the OCAC interface
uses Z3 5.3.3 with a separate 30 s satisfiability-query cap; it does not optimize
the objective or use the reference value to recover a witness.
