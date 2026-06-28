#!/usr/bin/env python3
"""Exactness / boundary experiment: separating ALL solver techniques by arithmetic.

The three paradigms use fundamentally different arithmetic, with different
*exactness guarantees and failure modes*:

  * float MILP (CBC/HiGHS/SCIP/CPLEX/Gurobi) -- IEEE-754 double precision.
    Integers above the 53-bit mantissa (> 2**53) cannot be represented exactly,
    so the objective and the *ranking* of candidate solutions silently lose
    precision: the solver returns a feasible solution that is EXACTLY sub-optimal
    while reporting it as optimal. Failure mode: SILENT WRONG ANSWER.

  * CP-SAT (OR-Tools) -- exact 64-bit integer arithmetic. Correct as long as all
    coefficients and the values reachable by any linear expression stay within
    int64 (~2**63). Beyond that it does NOT return a wrong answer: it rejects the
    model (status MODEL_INVALID). Failure mode: SAFE REFUSAL. Integer-only.

  * OMT (z3 / OptiMathSAT) -- exact arbitrary-precision rational arithmetic (GMP).
    Correct at ANY magnitude, unbounded, and handles true rationals. No failure.

This script sweeps the coefficient magnitude (BASE = 2**e for several e) over the
SAME small 0/1 knapsacks, computes the TRUE optimum by exact big-integer brute
force, and asks every solver to solve. For MILP/CP we read back the chosen items
and recompute the objective with exact Python integers; for OMT we read the
reported (exact) objective. Each (instance, solver) is classified as:
    exact   -- returned solution is exactly the true optimum
    wrong   -- returned a feasible but exactly-sub-optimal solution (silent error)
    refused -- solver declined the model (MODEL_INVALID / coefficient-range error)
    error   -- solver failed for another reason / no solution parsed

The magnitudes are chosen to cross every boundary:
    2**40  control  : < 2**53 and < 2**63  -> everyone exact
    2**54  : just past the double mantissa  -> float MILP starts failing
    2**60  : 8 items sum to ~2**63          -> CP-SAT hits its int64 limit
    2**90  : far beyond int64 (and 2**53)   -> only OMT stays exact

Run with the full-CPLEX environment so cplex/gurobi are unbounded:
    .venv-cplex/bin/python scripts/exact_experiment.py

Output: runs/exact/results.json (raw) + runs/exact/summary.json (per-magnitude
rates, the data backing the paper's exactness table) + a printed summary.
"""

import _bootstrap  # noqa: F401
import itertools
import json
import os
import random
import re
import subprocess
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OMT_BIN = os.path.join(REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin",
                       "optimathsat")
SCIP_EXACT_BIN = os.environ.get("SCIP_EXACT",
    os.path.join(REPO, "tools", "scip-exact", "scip"))

# Coefficient magnitudes (exponents of 2) crossing every arithmetic boundary.
#   40 : < 2**53 and < 2**63       -> representable; isolates tolerance/scaling
#   54 : just past the double mantissa (2**53)
#   60 : 8 items sum to ~2**63      -> CP-SAT's int64 limit
#  200 : far beyond any fixed precision -> OMT alone stays exact (unboundedness)
EXPONENTS = [40, 54, 60, 200]
SIZES = [8, 12]
SEEDS = range(5)


def gen(n, seed, base):
    """n items, value = base + small offset (offset in [0,7]); the offsets decide
    the true optimum but are *below the double ULP* once base >= 2**54, so a float
    solver cannot tell the items apart. Weights/capacity force picking a subset.
    Exact optimum by big-integer brute force (n small)."""
    rng = random.Random(seed)
    offs = [rng.randint(0, 7) for _ in range(n)]
    val = [base + o for o in offs]
    w = [rng.randint(1, 3) for _ in range(n)]
    C = max(w) + sum(sorted(w)[: n // 2])
    best = -1
    for r in range(n + 1):
        for combo in itertools.combinations(range(n), r):
            if sum(w[i] for i in combo) <= C:
                best = max(best, sum(val[i] for i in combo))
    return {"n": n, "seed": seed, "exp": base.bit_length() - 1,
            "val": val, "w": w, "C": C, "opt": best}


def _classify(sel, inst):
    """Given selected indices, recompute the EXACT objective with Python ints."""
    exact_obj = sum(inst["val"][i] for i in sel)
    feasible = sum(inst["w"][i] for i in sel) <= inst["C"]
    if not feasible:
        return {"status": "error", "value": exact_obj, "note": "infeasible"}
    ok = exact_obj == inst["opt"]
    return {"status": "exact" if ok else "wrong", "value": exact_obj,
            "gap_to_opt": inst["opt"] - exact_obj}


# ---------------- MILP (float) ----------------
def solve_milp_pulp(inst, backend):
    import pulp
    n = inst["n"]
    p = pulp.LpProblem("k", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{i}", cat="Binary") for i in range(n)]
    p += pulp.lpSum(inst["val"][i] * x[i] for i in range(n))
    p += pulp.lpSum(inst["w"][i] * x[i] for i in range(n)) <= inst["C"]
    # zero optimality-gap tolerance => MILP's BEST case: no early stop on the
    # relative-gap criterion, so any wrong answer is purely a precision effect.
    cls = {"cbc": pulp.PULP_CBC_CMD, "highs": pulp.HiGHS, "scip": pulp.SCIP_PY}[backend]
    kw = dict(gapRel=0, gapAbs=0)
    try:
        p.solve(cls(msg=0, **kw) if backend == "cbc" else cls(msg=False, **kw))
    except Exception as e:
        return {"status": "error", "note": str(e)[:80]}
    sel = [i for i in range(n) if (x[i].value() or 0) > 0.5]
    return _classify(sel, inst)


def solve_cplex(inst):
    """Full CPLEX via docplex (recognized API)."""
    try:
        from docplex.mp.model import Model
        n = inst["n"]
        m = Model("k"); m.context.cplex_parameters.threads = 1
        m.parameters.mip.tolerances.mipgap = 0.0
        m.parameters.mip.tolerances.absmipgap = 0.0
        x = m.binary_var_list(n)
        m.add(m.sum(inst["w"][i] * x[i] for i in range(n)) <= inst["C"])
        m.maximize(m.sum(inst["val"][i] * x[i] for i in range(n)))
        s = m.solve(log_output=False)
        if s is None:
            return {"status": "error", "note": "no solution"}
        sel = [i for i in range(n) if x[i].solution_value > 0.5]
        return _classify(sel, inst)
    except Exception as e:
        return {"status": "refused", "note": str(e)[:80]}


def solve_gurobi(inst):
    """Gurobi via gurobipy (native API)."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
        n = inst["n"]
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.Threads = 1
        m.Params.MIPGap = 0.0; m.Params.MIPGapAbs = 0.0
        x = m.addVars(n, vtype=GRB.BINARY)
        m.addConstr(gp.quicksum(inst["w"][i] * x[i] for i in range(n)) <= inst["C"])
        m.setObjective(gp.quicksum(inst["val"][i] * x[i] for i in range(n)), GRB.MAXIMIZE)
        m.optimize()
        if m.SolCount == 0:
            return {"status": "error", "note": f"status {m.Status}"}
        sel = [i for i in range(n) if x[i].X > 0.5]
        return _classify(sel, inst)
    except Exception as e:
        return {"status": "refused", "note": str(e)[:80]}


# ---------------- CP (int64) ----------------
def solve_cpsat(inst):
    from ortools.sat.python import cp_model
    n = inst["n"]
    md = cp_model.CpModel()
    x = [md.NewBoolVar(f"x{i}") for i in range(n)]
    md.Add(sum(inst["w"][i] * x[i] for i in range(n)) <= inst["C"])
    md.Maximize(sum(inst["val"][i] * x[i] for i in range(n)))
    s = cp_model.CpSolver()
    try:
        st = s.Solve(md)
    except Exception as e:                       # overflow rejected at build time
        return {"status": "refused", "note": str(e)[:80]}
    if st == cp_model.MODEL_INVALID:             # int64 range exceeded -> safe refusal
        return {"status": "refused", "note": "MODEL_INVALID (int64 range)"}
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "error", "note": f"status {s.StatusName(st)}"}
    sel = [i for i in range(n) if s.Value(x[i]) == 1]
    return _classify(sel, inst)


# ---------------- OMT (exact rational) ----------------
_OBJ = re.compile(r"\(\s*obj\s+(-?\d+)\s*\)")


def solve_omt(inst, binary):
    n = inst["n"]
    L = ["(set-option :produce-models true)", "(set-logic QF_LIA)"]
    for i in range(n):
        L += [f"(declare-fun x{i} () Int)", f"(assert (>= x{i} 0))",
              f"(assert (<= x{i} 1))"]
    w, val = inst["w"], inst["val"]
    L.append(f"(assert (<= (+ {' '.join(f'(* {w[i]} x{i})' for i in range(n))}) {inst['C']}))")
    L.append("(declare-fun obj () Int)")
    L.append(f"(assert (= obj (+ {' '.join(f'(* {val[i]} x{i})' for i in range(n))})))")
    L += ["(maximize obj)", "(check-sat)", "(get-objectives)"]
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write("\n".join(L)); f.close()
    cmd = [binary, f.name] if binary == "z3" else [binary, "-optimization=TRUE", f.name]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception as e:
        os.unlink(f.name)
        return {"status": "error", "note": str(e)[:80]}
    os.unlink(f.name)
    m = _OBJ.search(out)
    if not m:
        return {"status": "error", "note": "no objective parsed"}
    val = int(m.group(1))
    return {"status": "exact" if val == inst["opt"] else "wrong", "value": val}

# ---------------- exact-rational MILP (SCIP exact mode) ----------------
def solve_scip_exact(inst):
    """Exact rational MIP via SCIP's exact solving mode (SCIP>=10 built with
    EXACTSOLVE + GMP + exact SoPlex; see tools/README). Coefficients are written
    as exact integers in an LP file (SCIP's exact reader stores them as rationals,
    verified). Classified by SCIP's reported Exact Primal Bound vs the true opt.
    SCIP treats |value| >= numerics/infinity (~1e20) as infinite and refuses to
    read -> SAFE REFUSAL at very large magnitudes (it never returns a wrong
    answer)."""
    if not os.path.exists(SCIP_EXACT_BIN):
        return {"status": "error", "note": "exact-SCIP binary not found"}
    n = inst["n"]
    lp = ["Maximize",
          " obj: " + " + ".join(f"{inst['val'][i]} x{i}" for i in range(n)),
          "Subject to",
          " cap: " + " + ".join(f"{inst['w'][i]} x{i}" for i in range(n)) + f" <= {inst['C']}",
          "Binary", " " + " ".join(f"x{i}" for i in range(n)), "End"]
    f = tempfile.NamedTemporaryFile("w", suffix=".lp", delete=False)
    f.write("\n".join(lp)); f.close()
    try:
        out = subprocess.run([SCIP_EXACT_BIN, "-c", "set exact enable TRUE",
              "-c", f"read {f.name}", "-c", "optimize", "-c", "quit"],
              capture_output=True, text=True, timeout=120)
    except Exception as e:
        os.unlink(f.name); return {"status": "error", "note": str(e)[:80]}
    os.unlink(f.name)
    blob = out.stdout + out.stderr
    if "error reading file" in blob or "objective value is infinite" in blob:
        return {"status": "refused", "note": "coeff >= SCIP infinity (~1e20)"}
    m = re.search(r"Exact Primal Bound\s*:\s*(-?\d+)", out.stdout)
    if not m:
        return {"status": "error", "note": "no exact bound parsed"}
    val = int(m.group(1))
    return {"status": "exact" if val == inst["opt"] else "wrong", "value": val}


def solve_gurobi_quad(inst):
    """Gurobi with quad-precision simplex (NumericFocus=3, Quad=1) — tests whether
    Gurobi's higher-precision option recovers exactness. (Data: it does NOT — the
    coefficients are stored in double at model build, so the offset below the double
    ULP is already lost on input; Quad only affects the simplex computation.)"""
    try:
        import gurobipy as gp
        from gurobipy import GRB
        n = inst["n"]
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.Threads = 1
        m.Params.MIPGap = 0.0; m.Params.MIPGapAbs = 0.0
        m.Params.NumericFocus = 3; m.Params.Quad = 1
        x = m.addVars(n, vtype=GRB.BINARY)
        m.addConstr(gp.quicksum(inst["w"][i] * x[i] for i in range(n)) <= inst["C"])
        m.setObjective(gp.quicksum(inst["val"][i] * x[i] for i in range(n)), GRB.MAXIMIZE)
        m.optimize()
        if m.SolCount == 0:
            return {"status": "error", "note": f"status {m.Status}"}
        sel = [i for i in range(n) if x[i].X > 0.5]
        return _classify(sel, inst)
    except Exception as e:
        return {"status": "refused", "note": str(e)[:80]}


SOLVERS = [
    ("z3",          "OMT",  lambda inst: solve_omt(inst, "z3")),
    ("optimathsat", "OMT",  lambda inst: solve_omt(inst, OMT_BIN)),
    ("cpsat",       "CP",   solve_cpsat),
    ("cbc",         "MILP", lambda inst: solve_milp_pulp(inst, "cbc")),
    ("highs",       "MILP", lambda inst: solve_milp_pulp(inst, "highs")),
    ("scip",        "MILP", lambda inst: solve_milp_pulp(inst, "scip")),
    ("cplex",       "MILP", solve_cplex),
    ("gurobi",      "MILP", solve_gurobi),
    ("gurobi-quad", "MILP", solve_gurobi_quad),
    ("scip-exact",  "MILP", solve_scip_exact),
]


def main():
    out = os.path.join(REPO, "runs", "exact")
    os.makedirs(out, exist_ok=True)

    rows = []
    for e in EXPONENTS:
        base = 2 ** e
        for n in SIZES:
            for seed in SEEDS:
                inst = gen(n, seed, base)
                rec = {"exp": e, "n": n, "seed": seed, "true_opt": inst["opt"],
                       "solvers": {}}
                for name, _para, fn in SOLVERS:
                    rec["solvers"][name] = fn(inst)
                rows.append(rec)
                tag = "  ".join(
                    f"{name}={rec['solvers'][name]['status'][:5]}"
                    for name, _p, _f in SOLVERS)
                print(f"2^{e:<3} n={n} s={seed}  {tag}")

    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)

    # ---- aggregate: per (solver, exponent) status counts ----
    summary = {}  # name -> exp -> {exact,wrong,refused,error,total}
    for rec in rows:
        for name, d in rec["solvers"].items():
            cell = summary.setdefault(name, {}).setdefault(
                rec["exp"], {"exact": 0, "wrong": 0, "refused": 0, "error": 0, "total": 0})
            cell["total"] += 1
            cell[d["status"]] = cell.get(d["status"], 0) + 1
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1)

    # ---- printed table ----
    SYM = {"exact": "OK", "wrong": "WRONG", "refused": "REFUSE", "error": "ERR"}
    print("\n=== exact-optimal rate by coefficient magnitude "
          f"(coeff = 2^e + offset; double mantissa = 2^53, int64 ~ 2^63) ===")
    hdr = "  ".join(f"2^{e}" for e in EXPONENTS)
    print(f"  {'paradigm':9}{'solver':13}{hdr}     dominant failure")
    para_of = {name: p for name, p, _ in SOLVERS}
    for name, _p, _f in SOLVERS:
        cells, modes = [], set()
        for e in EXPONENTS:
            c = summary[name][e]
            cells.append(f"{c['exact']}/{c['total']}")
            if c["exact"] < c["total"]:
                m = max(("wrong", "refused", "error"), key=lambda k: c.get(k, 0))
                if c.get(m, 0):
                    modes.add(m)
        mode = ("silent-wrong" if "wrong" in modes else
                "safe-refusal" if "refused" in modes else
                "error" if "error" in modes else "-- none --")
        row = "  ".join(f"{x:>5}" for x in cells)
        print(f"  {para_of[name]:9}{name:13}{row}     {mode}")
    print(f"\nWrote {os.path.relpath(out, REPO)}/results.json + summary.json")


if __name__ == "__main__":
    main()
