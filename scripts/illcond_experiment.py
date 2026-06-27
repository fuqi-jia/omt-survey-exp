#!/usr/bin/env python3
"""Ill-conditioning experiment: float MILP fails on a benign small-coefficient
   problem due to accumulated rounding; exact OMT recovers the true solution.

This is the genuine floating-point counterpart to the large-coefficient
representation experiment (tab:exp-exact). The data here is SMALL and FRACTIONAL
(all coefficients in (0,1]) -- no large integers, no constant planted inside the
feasibility tolerance. The error arises purely from IEEE-754 double accumulating
rounding while solving an ILL-CONDITIONED system (the conclusion's "病态条件").

Instance (the classic Hilbert system, condition number ~ e^{3.5 n}):
    H[i][j] = 1/(i+j+1),     b = H * 1  (the vector of row sums).
    Recover integer x in {0,1,2}^n with  H x = b.
Since H is invertible, the unique real (hence integer) solution is x = 1 (ones).
A float MILP rounds H to double; once cond(H) approaches 1/eps the rounded system
no longer pins x to ones, so the solver either returns a WRONG x (accepted within
its feasibility tolerance) or declares the exactly-feasible system INFEASIBLE.
Exact OMT (z3 / OptiMathSAT over QF_LIRA, rational arithmetic) is unaffected.

Run:  .venv-cplex/bin/python scripts/illcond_experiment.py
Output: runs/illcond/results.json + a printed table.
"""

import json
import os
import re
import subprocess
import tempfile
from fractions import Fraction as F

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OMT_BIN = os.path.join(REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin",
                       "optimathsat")
SIZES = [6, 8, 10, 12, 14, 16]
UB = 2


def hilbert(n):
    H = [[F(1, i + j + 1) for j in range(n)] for i in range(n)]
    b = [sum(H[i]) for i in range(n)]          # = H * ones  (exact)
    return H, b


def classify(x, n, status_ok=True):
    """x: list of ints or None. Returns one of correct/wrong/infeasible/error."""
    if x is None:
        return "infeasible" if status_ok is False else "error"
    return "correct" if all(int(v) == 1 for v in x) else "wrong"


# ---- float MILP: H rounded to double ----
def milp_pulp(n, backend):
    import pulp
    H, b = hilbert(n)
    p = pulp.LpProblem("h", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x{j}", 0, UB, cat="Integer") for j in range(n)]
    p += 0
    for i in range(n):
        p += pulp.lpSum(float(H[i][j]) * x[j] for j in range(n)) == float(b[i])
    cls = {"cbc": pulp.PULP_CBC_CMD, "highs": pulp.HiGHS, "scip": pulp.SCIP_PY}[backend]
    try:
        p.solve(cls(msg=0) if backend == "cbc" else cls(msg=False))
    except Exception:
        return "error"
    st = pulp.LpStatus[p.status]
    if st != "Optimal":
        return "infeasible" if "nfeasible" in st else "error"
    return classify([round(v.value()) for v in x], n)


def gurobi(n):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        H, b = hilbert(n)
        m = gp.Model(); m.Params.OutputFlag = 0
        x = [m.addVar(0, UB, vtype=GRB.INTEGER) for _ in range(n)]
        for i in range(n):
            m.addConstr(gp.quicksum(float(H[i][j]) * x[j] for j in range(n)) == float(b[i]))
        m.optimize()
        if m.SolCount == 0:
            return "infeasible" if m.Status == GRB.INFEASIBLE else "error"
        return classify([round(v.X) for v in x], n)
    except Exception:
        return "error"


def cplex(n):
    try:
        from docplex.mp.model import Model
        H, b = hilbert(n)
        m = Model(); x = [m.integer_var(0, UB) for _ in range(n)]
        for i in range(n):
            m.add(m.sum(float(H[i][j]) * x[j] for j in range(n)) == float(b[i]))
        s = m.solve(log_output=False)
        if s is None:
            return "infeasible"
        return classify([round(x[j].solution_value) for j in range(n)], n)
    except Exception:
        return "error"


# ---- exact OMT: QF_LIRA, rational coefficients ----
def omt(n, binary):
    H, b = hilbert(n)
    L = ["(set-option :produce-models true)", "(set-logic QF_LIRA)"]
    for j in range(n):
        L += [f"(declare-fun x{j} () Int)", f"(assert (>= x{j} 0))", f"(assert (<= x{j} {UB}))"]
    for i in range(n):
        terms = " ".join(f"(* (/ {H[i][j].numerator} {H[i][j].denominator}) x{j})"
                         for j in range(n))
        L.append(f"(assert (= (+ {terms}) (/ {b[i].numerator} {b[i].denominator})))")
    L += ["(check-sat)", "(get-value (" + " ".join(f"x{j}" for j in range(n)) + "))"]
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write("\n".join(L)); f.close()
    cmd = [binary, f.name]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        os.unlink(f.name); return "error"
    os.unlink(f.name)
    if out.strip().startswith("unsat"):
        return "infeasible"
    vals = re.findall(r"\(x\d+\s+(\d+)\)", out)
    return classify(vals, n) if vals else "error"


SOLVERS = [
    ("z3",          "OMT",  lambda n: omt(n, "z3")),
    ("optimathsat", "OMT",  lambda n: omt(n, OMT_BIN)),
    ("cbc",         "MILP", lambda n: milp_pulp(n, "cbc")),
    ("highs",       "MILP", lambda n: milp_pulp(n, "highs")),
    ("scip",        "MILP", lambda n: milp_pulp(n, "scip")),
    ("gurobi",      "MILP", gurobi),
    ("cplex",       "MILP", cplex),
]
_SYM = {"correct": "OK", "wrong": "WRONG", "infeasible": "f.INFEAS", "error": "err"}


def main():
    out = os.path.join(REPO, "runs", "illcond")
    os.makedirs(out, exist_ok=True)
    rows = []
    print("Hilbert integer recovery  H[i][j]=1/(i+j+1),  H x = H*1,  x in {0,1,2}.")
    print("True (unique) solution x = ones. Coefficients are small fractions (<=1).\n")
    print(f"  {'solver':12}" + "".join(f"{('n=%d' % n):>9}" for n in SIZES))
    for name, para, fn in SOLVERS:
        rec = {"solver": name, "paradigm": para, "by_n": {}}
        cells = []
        for n in SIZES:
            st = fn(n); rec["by_n"][str(n)] = st; cells.append(_SYM[st])
        rows.append(rec)
        print(f"  {name:12}" + "".join(f"{c:>9}" for c in cells))
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)
    print("\nWRONG = returned x != ones but reported feasible/optimal (accepted within tolerance);")
    print("f.INFEAS = declared the exactly-feasible system infeasible. Both are float failures.")
    print(f"Wrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
