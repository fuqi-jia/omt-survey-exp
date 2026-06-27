#!/usr/bin/env python3
"""Floating-point experiment: MILP satisfies constraints only within tolerance.

Distinct from the large-coefficient *objective* error (exact_experiment.py /
tab:exp-exact). Here the issue is the IEEE-754 + tolerance NUMERICAL CORE of MILP:
a constraint is accepted as long as it is satisfied within an absolute feasibility
tolerance (typically ~1e-6), so a REAL-VALUED boundary that lies within that
tolerance of an integer is silently crossed.

Family (one deterministic instance per real offset delta):
    maximize  x      s.t.  x <= 1 - delta,    x in {0,1} integer.
delta is a small REAL (floating-point) offset, NOT a large integer. The exact
optimum is x = 0 (x = 1 needs 1 <= 1 - delta, i.e. delta <= 0). A float MILP whose
feasibility tolerance exceeds delta accepts x = 1, returning an EXACTLY-INFEASIBLE
"optimum". Exact-rational OMT (LRA/LIA over the rationals) encodes delta = p/q and
is correct for every delta.

The MILP model is given the real boundary 1 - delta directly (float coefficient);
the OMT model is given the exact rational q*x <= q - p. This contrast isolates the
floating-point feasibility tolerance: MILP flips from correct to infeasible right
at its tolerance (~1e-6), commercial solvers included.

Run:  .venv-cplex/bin/python scripts/float_experiment.py
Output: runs/float/results.json + a printed table.
"""

import json
import os
import re
import subprocess
import tempfile
from fractions import Fraction

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OMT_BIN = os.path.join(REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin",
                       "optimathsat")
# real offsets straddling the ~1e-6 feasibility tolerance
DELTAS = [1e-4, 1e-5, 1e-6, 1e-7, 1e-9, 1e-12]


def classify(x):
    if x is None:
        return "error"
    return "exact-opt" if x == 0 else "infeasible"   # x>=1 exactly violates x<=1-delta


# ---- float MILP: given the real boundary 1 - delta directly ----
def milp_pulp(delta, backend):
    import pulp
    p = pulp.LpProblem("t", pulp.LpMaximize)
    x = pulp.LpVariable("x", lowBound=0, upBound=1, cat="Integer")
    p += x
    p += x <= 1 - delta
    cls = {"cbc": pulp.PULP_CBC_CMD, "highs": pulp.HiGHS, "scip": pulp.SCIP_PY}[backend]
    try:
        p.solve(cls(msg=0) if backend == "cbc" else cls(msg=False))
    except Exception:
        return None
    v = x.value()
    return None if v is None else int(round(v))


def gurobi(delta):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0
        x = m.addVar(lb=0, ub=1, vtype=GRB.INTEGER); m.setObjective(x, GRB.MAXIMIZE)
        m.addConstr(x <= 1 - delta); m.optimize()
        return int(round(x.X)) if m.SolCount else None
    except Exception:
        return None


def cplex(delta):
    try:
        from docplex.mp.model import Model
        m = Model(); x = m.integer_var(0, 1); m.maximize(x); m.add(x <= 1 - delta)
        s = m.solve(log_output=False)
        return int(round(x.solution_value)) if s else None
    except Exception:
        return None


# ---- exact OMT: given delta = p/q as an exact rational, x <= 1 - p/q  <=>  q*x <= q-p ----
_VAL = re.compile(r"\(\s*x\s+(-?\d+)\s*\)")


def omt(delta, binary):
    fr = Fraction(delta).limit_denominator(10 ** 18)
    q, p = fr.denominator, fr.numerator           # delta = p/q
    L = ["(set-option :produce-models true)", "(set-logic QF_LIA)",
         "(declare-fun x () Int)", "(assert (>= x 0))", "(assert (<= x 1))",
         f"(assert (<= (* {q} x) {q - p}))", "(maximize x)",
         "(check-sat)", "(get-value (x))"]
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write("\n".join(L)); f.close()
    cmd = [binary, f.name] if binary == "z3" else [binary, "-optimization=TRUE", f.name]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        os.unlink(f.name); return None
    os.unlink(f.name)
    m = _VAL.search(out)
    return int(m.group(1)) if m else None


SOLVERS = [
    ("z3",          "OMT",  lambda d: omt(d, "z3")),
    ("optimathsat", "OMT",  lambda d: omt(d, OMT_BIN)),
    ("cbc",         "MILP", lambda d: milp_pulp(d, "cbc")),
    ("highs",       "MILP", lambda d: milp_pulp(d, "highs")),
    ("scip",        "MILP", lambda d: milp_pulp(d, "scip")),
    ("gurobi",      "MILP", gurobi),
    ("cplex",       "MILP", cplex),
]


def main():
    out = os.path.join(REPO, "runs", "float")
    os.makedirs(out, exist_ok=True)
    rows = []
    print("max x  s.t.  x <= 1 - delta,  x in {0,1} int.  True optimum x=0 (delta real).\n")
    print(f"  {'solver':12}" + "".join(f"{('%.0e' % d):>10}" for d in DELTAS))
    for name, para, fn in SOLVERS:
        rec = {"solver": name, "paradigm": para, "by_delta": {}}
        cells = []
        for d in DELTAS:
            x = fn(d); st = classify(x)
            rec["by_delta"][f"{d:.0e}"] = {"x": x, "status": st}
            cells.append({"exact-opt": "OK", "infeasible": "INFEAS", "error": "err"}[st])
        rows.append(rec)
        print(f"  {name:12}" + "".join(f"{c:>10}" for c in cells))
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)
    print("\nINFEAS = returned x=1, which EXACTLY violates x<=1-delta (accepted within the\n"
          "absolute feasibility tolerance ~1e-6). OMT encodes delta=p/q exactly and is correct.")
    print(f"Wrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
