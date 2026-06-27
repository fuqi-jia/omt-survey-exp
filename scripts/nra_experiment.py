#!/usr/bin/env python3
"""NRA experiment: OMT(NRA) vs nonlinear programming (NLP) vs global MINLP.

Demonstrates that nonconvex / exact nonlinear optimization is a genuine strength
of OMT(NRA). Three solver kinds:
  * OMT(NRA): CDCL(OCAC) -- the complete OMT(NRA) engine (a cvc5 fork). Exact:
    returns the optimum as an algebraic number (e.g. sqrt(2)) and is GLOBAL.
  * local NLP: scipy.optimize (SLSQP) -- smooth local optimization; on a
    nonconvex problem it converges to a LOCAL optimum that depends on the start.
  * global MINLP: Gurobi (NonConvex=2) and SCIP -- spatial branch-and-bound,
    GLOBAL but floating-point (epsilon-approximate, no exact algebraic value).

Two instance kinds:
  (A) exact/irrational optimum:  max x  s.t.  x^2 <= k, x >= 0   ->  x* = sqrt(k).
      Convex, so every solver finds the global; the point is that only OMT(NRA)
      reports it EXACTLY (algebraic), the others give a float approximation.
  (B) nonconvex local trap:  min x  s.t. (2x-5)^2 >= 9, 0 <= x <= 5.
      Feasible set {x<=1} U {x>=4}; global x*=0. A local NLP started at x=5 is
      trapped at the local optimum x=4; OMT(NRA) and global MINLP find 0.

Run with the full-CPLEX/Gurobi env:  .venv-cplex/bin/python scripts/nra_experiment.py
(OCAC binary path via $OCAC or the default build location.)
Output: runs/nra/results.json + a printed table.
"""

import json
import math
import os
import re
import subprocess
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OMS = os.path.join(REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin", "optimathsat")
# CDCL(OCAC) binary -- the complete OMT(NRA) solver. Set $OCAC, or drop the
# prebuilt static Linux x86-64 binary at tools/cdcl_ocac/cvc5. Download it from:
#   https://github.com/fuqi-jia/cdcl_ocac/releases/tag/v1.0.4-ocac-static
OCAC = os.environ.get("OCAC") or os.path.join(REPO, "tools", "cdcl_ocac", "cvc5")


# ---------------- instances ----------------
# (A) max x s.t. x^2<=k, x>=0  -> sqrt(k)
A_KS = [2, 3, 5, 7]
# (B) min x s.t. (2x-5)^2>=9, 0<=x<=5 -> 0 (local trap at 4); parametrized by gap center
B_INSTS = [(5, 9), (7, 16), (9, 25)]  # (a,b): (2x-a)^2>=b ; global x=0


def true_sqrt(k):
    return math.sqrt(k)


# ---------------- OMT(NRA): CDCL(OCAC) ----------------
def ocac_solve(smt):
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write(smt); f.close()
    try:
        out = subprocess.run([OCAC, f.name], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:
        os.unlink(f.name); return ("error", str(e)[:40])
    os.unlink(f.name)
    if "real_algebraic_number" in out:
        m = re.search(r"\(([-\d/]+),\s*([-\d/]+)\)>", out)   # bracketing interval
        return ("algebraic", out.strip())
    m = re.search(r"\(x\s+(\(/\s*-?\d+\s+\d+\)|-?\d+(?:\.\d+)?)\)", out)
    if m:
        return ("exact", m.group(1))
    return ("unknown", out.strip()[:60])


def ocac_A(k):
    return ocac_solve(f"""(set-logic OMT_QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= (* x x) {k})))
(maximize x)
(check-sat)
(get-objectives)
""")


def ocac_B(a, b):
    return ocac_solve(f"""(set-logic OMT_QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= x 5) (>= (* (- (* 2 x) {a}) (- (* 2 x) {a})) {b})))
(minimize x)
(check-sat)
(get-objectives)
""")


# ---------------- incumbent OMT(NRA): OptiMathSAT (incremental linearization) ----------------
def oms_solve(smt):
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write(smt); f.close()
    try:
        out = subprocess.run([OMS, "-optimization=TRUE", f.name],
                             capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        os.unlink(f.name); return "T/O"
    except Exception:
        os.unlink(f.name); return "error"
    os.unlink(f.name)
    m = re.search(r"\(x\s+([-\d./eE+]+)\)", out)
    return m.group(1) if m else "unknown"


def oms_A(k):
    return oms_solve(f"""(set-option :produce-models true)
(set-logic QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= (* x x) {k})))
(maximize x)
(check-sat)
(get-objectives)
""")


def oms_B(a, b):
    return oms_solve(f"""(set-option :produce-models true)
(set-logic QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= x 5) (>= (* (- (* 2 x) {a}) (- (* 2 x) {a})) {b})))
(minimize x)
(check-sat)
(get-objectives)
""")


# ---------------- local NLP: scipy ----------------
def scipy_A(k):
    from scipy.optimize import minimize
    r = minimize(lambda v: -v[0], [0.5], bounds=[(0, None)],
                 constraints=[{"type": "ineq", "fun": lambda v: k - v[0] ** 2}], method="SLSQP")
    return r.x[0]


def scipy_B(a, b, start):
    from scipy.optimize import minimize
    r = minimize(lambda v: v[0], [start], bounds=[(0, 5)],
                 constraints=[{"type": "ineq", "fun": lambda v: (2 * v[0] - a) ** 2 - b}], method="SLSQP")
    return r.x[0]


# ---------------- global MINLP: Gurobi (NonConvex=2) ----------------
def gurobi_A(k):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.NonConvex = 2
        x = m.addVar(lb=0, ub=10); m.setObjective(x, GRB.MAXIMIZE)
        m.addConstr(x * x <= k); m.optimize()
        return x.X if m.SolCount else None
    except Exception as e:
        return None


def gurobi_B(a, b):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.NonConvex = 2
        x = m.addVar(lb=0, ub=5); m.setObjective(x, GRB.MINIMIZE)
        m.addConstr((2 * x - a) * (2 * x - a) >= b); m.optimize()
        return x.X if m.SolCount else None
    except Exception:
        return None


def fmt(v):
    return "--" if v is None else f"{v:.4f}"


def main():
    out = os.path.join(REPO, "runs", "nra"); os.makedirs(out, exist_ok=True)
    rows = []
    print(f"OCAC = {OCAC}\n")
    print("== (A) max x s.t. x^2<=k  (x*=sqrt k, irrational; convex -> all global) ==")
    print(f"  {'k':>3} {'true':>9} {'OCAC':>12} {'OptiMSAT':>10} {'scipy':>9} {'gurobi':>9}")
    for k in A_KS:
        oc = ocac_A(k); om = oms_A(k); sp = scipy_A(k); gu = gurobi_A(k)
        exact = oc[0] == "algebraic" or oc[0] == "exact"
        rows.append({"inst": f"A_sqrt{k}", "true": true_sqrt(k), "ocac": oc[0],
                     "ocac_exact": exact, "optimathsat": om, "scipy": sp, "gurobi": gu})
        tag = "algebraic" if oc[0] == "algebraic" else oc[0]
        print(f"  {k:>3} {true_sqrt(k):>9.4f} {tag:>12} {om:>10} {fmt(sp):>9} {fmt(gu):>9}")
    print("\n== (B) min x s.t. (2x-a)^2>=b  (nonconvex; global x*=0, local trap x=a/2-...) ==")
    print(f"  {'(a,b)':>8} {'global':>7} {'OCAC':>7} {'scipy@hi':>9} {'scipy@lo':>9} {'gurobi':>8}")
    for (a, b) in B_INSTS:
        oc = ocac_B(a, b); om = oms_B(a, b); sp_hi = scipy_B(a, b, 5.0); sp_lo = scipy_B(a, b, 0.2); gu = gurobi_B(a, b)
        ocv = oc[1] if oc[0] in ("exact",) else oc[0]
        rows.append({"inst": f"B_{a}_{b}", "global": 0.0, "ocac": oc[0], "ocac_val": oc[1],
                     "optimathsat": om, "scipy_hi": sp_hi, "scipy_lo": sp_lo, "gurobi": gu})
        print(f"  ({a},{b})  {0.0:>6.1f} {str(ocv):>7} {str(om):>9} {fmt(sp_hi):>9} {fmt(sp_lo):>9} {fmt(gu):>8}")
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)
    print(f"\nscipy@hi = local NLP started at x=5 (trap); scipy@lo = started at x=0.2.")
    print(f"Wrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
