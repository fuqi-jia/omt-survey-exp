#!/usr/bin/env python3
"""Exactness experiment: floating-point MILP vs exact OMT / integer CP.

MILP solvers work in double precision and satisfy constraints only within a
feasibility/integrality tolerance. With large integer coefficients (beyond the
53-bit mantissa, i.e. > 2**53) the objective and the ranking of solutions lose
precision, so a float MILP can return a solution that is *exactly* sub-optimal
(or, with tolerances, slightly infeasible). OMT/SMT use exact arithmetic
(rational LIA), and CP-SAT uses 64-bit integers -- both are exact.

This script builds small 0/1 knapsacks with large coefficients, computes the
TRUE optimum by exact brute force, then asks each solver to solve. For MILP/CP
we read back the chosen items and recompute the objective with exact Python
integers; for OMT we read the reported (exact) objective. We then report, per
solver, the rate at which the returned solution is EXACTLY optimal.

Output: runs/exact/results.json + a printed summary.  Self-contained.
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
BASE = 2 ** 54  # values = BASE + small offset; pair sums ~2**55 (double ULP = 8)


def gen(n, seed):
    """n items, value=BASE+offset (offset in [0,7], below the sum's ULP),
    unit-ish weights, capacity forces picking a subset; exact optimum by brute
    force. The offsets (which decide the true optimum) are invisible to double."""
    rng = random.Random(seed)
    offs = [rng.randint(0, 7) for _ in range(n)]
    val = [BASE + o for o in offs]
    w = [rng.randint(1, 3) for _ in range(n)]
    C = max(w) + sum(sorted(w)[: n // 2])  # room for ~half the items
    # exact brute-force optimum (n small)
    best = -1
    for r in range(n + 1):
        for combo in itertools.combinations(range(n), r):
            if sum(w[i] for i in combo) <= C:
                best = max(best, sum(val[i] for i in combo))
    return {"n": n, "seed": seed, "val": val, "w": w, "C": C, "opt": best}


# ---------------- solvers ----------------
def solve_milp(inst, backend):
    import pulp
    val, w, C, n = inst["val"], inst["w"], inst["C"], inst["n"]
    p = pulp.LpProblem("k", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{i}", cat="Binary") for i in range(n)]
    p += pulp.lpSum(val[i] * x[i] for i in range(n))
    p += pulp.lpSum(w[i] * x[i] for i in range(n)) <= C
    solver = {"cbc": pulp.PULP_CBC_CMD, "highs": pulp.HiGHS,
              "scip": pulp.SCIP_PY}[backend]
    try:
        p.solve(solver(msg=False) if backend != "cbc" else solver(msg=0))
    except Exception as e:
        return None, str(e)[:60]
    sel = [i for i in range(n) if (x[i].value() or 0) > 0.5]
    # EXACT objective of the returned selection (Python ints)
    exact_obj = sum(val[i] for i in sel)
    feasible = sum(w[i] for i in sel) <= C
    return {"sel": sel, "exact_obj": exact_obj, "feasible": feasible}, None


def solve_cpsat(inst):
    from ortools.sat.python import cp_model
    val, w, C, n = inst["val"], inst["w"], inst["C"], inst["n"]
    md = cp_model.CpModel()
    x = [md.NewBoolVar(f"x{i}") for i in range(n)]
    md.Add(sum(w[i] * x[i] for i in range(n)) <= C)
    md.Maximize(sum(val[i] * x[i] for i in range(n)))
    s = cp_model.CpSolver()
    s.Solve(md)
    sel = [i for i in range(n) if s.Value(x[i]) == 1]
    return {"sel": sel, "exact_obj": sum(val[i] for i in sel),
            "feasible": sum(w[i] for i in sel) <= C}


_OBJ = re.compile(r"\(\s*obj\s+(-?\d+)\s*\)")


def solve_omt(inst, binary):
    val, w, C, n = inst["val"], inst["w"], inst["C"], inst["n"]
    L = ["(set-option :produce-models true)", "(set-logic QF_LIA)"]
    for i in range(n):
        L += [f"(declare-fun x{i} () Int)", f"(assert (>= x{i} 0))",
              f"(assert (<= x{i} 1))"]
    L.append(f"(assert (<= (+ {' '.join(f'(* {w[i]} x{i})' for i in range(n))}) {C}))")
    L.append("(declare-fun obj () Int)")
    L.append(f"(assert (= obj (+ {' '.join(f'(* {val[i]} x{i})' for i in range(n))})))")
    L += ["(maximize obj)", "(check-sat)", "(get-objectives)"]
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write("\n".join(L)); f.close()
    cmd = [binary, f.name] if binary == "z3" else [binary, "-optimization=TRUE", f.name]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    finally:
        os.unlink(f.name)
    m = _OBJ.search(out)
    if not m:
        return None
    # OMT objective is exact; treat it as the solver's (exact) result value
    return {"reported_exact_obj": int(m.group(1))}


def main():
    out = os.path.join(REPO, "runs", "exact")
    os.makedirs(out, exist_ok=True)
    sizes = [8, 12, 16]
    seeds = range(5)
    milp_backends = ["cbc", "highs", "scip"]

    rows = []
    for n in sizes:
        for seed in seeds:
            inst = gen(n, seed)
            opt = inst["opt"]
            rec = {"n": n, "seed": seed, "true_opt": opt, "solvers": {}}
            # OMT (exact)
            for omt in [("z3", "z3"), ("optimathsat",
                        os.path.join(REPO, "tools",
                                     "optimathsat-1.7.4-linux-64-bit", "bin",
                                     "optimathsat"))]:
                r = solve_omt(inst, omt[1])
                rec["solvers"][omt[0]] = {
                    "exact_optimal": (r is not None
                                      and r["reported_exact_obj"] == opt),
                    "value": (r or {}).get("reported_exact_obj")}
            # MILP (float)
            for be in milp_backends:
                r, err = solve_milp(inst, be)
                if r is None:
                    rec["solvers"][be] = {"exact_optimal": False, "error": err}
                else:
                    rec["solvers"][be] = {
                        "exact_optimal": r["feasible"] and r["exact_obj"] == opt,
                        "value": r["exact_obj"], "feasible": r["feasible"],
                        "gap_to_opt": opt - r["exact_obj"]}
            # CP-SAT (int64)
            r = solve_cpsat(inst)
            rec["solvers"]["cpsat"] = {
                "exact_optimal": r["feasible"] and r["exact_obj"] == opt,
                "value": r["exact_obj"]}
            rows.append(rec)
            print(f"n={n} seed={seed} opt={opt}  " + "  ".join(
                f"{s}={'OK' if d['exact_optimal'] else 'WRONG'}"
                for s, d in rec["solvers"].items()))

    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)

    # aggregate exact-optimal rate
    soln = {}
    for rec in rows:
        for s, d in rec["solvers"].items():
            c = soln.setdefault(s, [0, 0])
            c[1] += 1
            c[0] += 1 if d["exact_optimal"] else 0
    print("\n=== exact-optimal rate (returned solution is EXACTLY optimal) ===")
    for s in ["z3", "optimathsat", "cbc", "highs", "scip", "cpsat"]:
        if s in soln:
            print(f"  {s:12} {soln[s][0]:>2}/{soln[s][1]}")
    print(f"\nValues are integers > 2**53 = {2**53}; MILP stores them as doubles.")
    print(f"Wrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
