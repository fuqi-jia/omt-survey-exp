# Nonconvex instances with irrational optima

All nine parameter combinations were fixed before solver runs. Every instance
has rational input coefficients, an irrational attained optimum, and two
feasible points whose midpoint is infeasible. Formulae, exact reference
expressions, reference vectors and midpoint certificates are stored in JSON.

## A: coupled quadratic constraints

Minimize `x+2y` over `0<=x,y<=r`, `xy>=1`, `x^2+y^2>=r`, for `r=5,8,13`.
Let `s=sqrt(r+2)`, `d=sqrt(r-2)`. The optimum is `(3s-d)/2`, attained at
`((s+d)/2,(s-d)/2)`. The swapped point is a distinct, worse local minimum.
Their midpoint violates the radial constraint.

For a global bound, set `S=x+y`. The constraints imply `S>=sqrt(r+2)` and
`|x-y|<=sqrt(S^2-4)`. Hence `x+2y >= (3S-sqrt(S^2-4))/2`; the right side is
increasing on the relevant interval. The stated intersection attains this bound.

## B: quartic constraints and two components

Minimize `x+y/10` over `-4<=x<=4`, `1<=y<=ceil(sqrt(b))`,
`(x^2-a)^2+y^2<=b`, for `(a,b)=(3,3),(4,6),(5,8)`.
The common encoding uses `q=x^2` for every solver. Its nonconvex quadratic
equality is retained; the quartic is not replaced by a convex inequality.

Since `y>=1`, `q<=a+sqrt(b-1)`. Thus the objective is bounded below by
`-sqrt(a+sqrt(b-1))+1/10`, attained at `y=1` on the negative component.
The positive component has a different local minimum. Points
`(+sqrt(a),1)` and `(-sqrt(a),1)` are feasible while their midpoint is not.

## C: OR between nonconvex branches

Minimize `x+2y` over `0<=x,y<=U`, `xy>=1` and

```text
(x^2+y^2>=r0 AND y<=1) OR (x^2+y^2>=r1 AND x<=1)
```

Here `(r0,r1)=(5,5),(29,5),(29,8)` and
`U=1+ceil(sqrt(max(r0,r1)))`. Each branch is nonconvex. Both branch optima
are given by their circle/hyperbola intersection: `v_minus(r0)` and
`v_plus(r1)`, where `v_plus/minus(r)=(3sqrt(r+2) +/- sqrt(r-2))/2`.
The union optimum is their minimum; different instances select different
branches. Monotonicity of `x+2y` on the two boundary pieces proves these values
for the declared parameters (`r>=5`).

Gurobi/Couenne use the exact binary encoding
`x^2+y^2>=r0+(r1-r0)d`, `y<=1+(U-1)d`, `x<=U-(U-1)d`, with `d` binary.
Its continuous relaxation contains a reverse-convex quadratic constraint.

## Protocol and outcomes

All five global tools run all nine instances. IPOPT and SLSQP each run both
initializations on A/B: `(r,1)` versus `(1,r)`, and
`(-sqrt(a),1,a)` versus `(+sqrt(a),1,a)` for `(x,y,q)`.
Global numerical tools retain the earlier midpoint initialization rule.
There are **69 formal calls**, each with 120 s, one thread and 4 GB.

Exact values are checked against the analytic radical expression. A separate
80-digit Decimal calculation checks each numerical reference. Feasibility and
objective tolerance remain `1e-6`. Native termination status is retained
separately from the candidate-vector check: Couenne reports infeasibility on
`C_r29_5`, although its solution file contains a nearby candidate. Three repeated
calls with byte-identical NL inputs reproduce this status. The manuscript table
records **infeasible**, as returned by the solver.

Commands and full outputs: `scripts/nra_irrational_20261102.py`,
`scripts/nra_irrational_gurobi_20261102.py`,
`scripts/audit_nra_irrational_20261102.py` and `runs/nra_irrational_20261102/`.
