#!/usr/bin/env python3
"""Full-Gurobi large-scale linear comparison (runs on WINDOWS).

Gurobi's full license here is NODE-locked to the Windows host, so it validates
only on Windows -- not in WSL2 (different host id). This standalone script runs
the pure-linear families (gap, knapsack) at sizes BEYOND the 2000-variable cap of
Gurobi's free restricted license, to show that a commercial MILP solver cruises
on large linear problems (the regime where OMT times out -- see the WSL runs).

Design notes:
  * Self-contained: needs only `gurobipy` + the stdlib. The gap/knapsack spec
    builders are copied VERBATIM from experiments/benchmarks/families.py so the
    instances are byte-identical to the WSL runs (same seed -> same data), yet we
    avoid importing the experiment package (which pulls in psutil / Unix-only
    `resource`, unavailable/awkward on Windows).
  * Timing discipline: only the solve call is timed; model construction is
    excluded (consistent with the WSL runner).
  * Output: runs/gurobi_win/results.json + a printed table.

Run via scripts/run_gurobi_windows.ps1 (sets GRB_LICENSE_FILE + a venv).
"""

import json
import os
import random
import time

import gurobipy as gp
from gurobipy import GRB

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Sizes chosen so the larger ones exceed the 2000-var restricted-license cap
# (marked in the output), where only the full license can solve.
SIZES = {"gap": [80, 160], "knapsack": [2000, 4000, 8000]}
SEEDS = [0, 1, 2]
TIMELIMIT = 120.0
RESTRICTED_CAP = 2000  # Gurobi free/pip restricted license variable limit


# ---- spec builders copied verbatim from experiments/benchmarks/families.py ----
def spec_gap(n, seed):
    rng = random.Random(seed)
    m = max(2, n // 4)
    c = [[rng.randint(1, 20) for _ in range(m)] for _ in range(n)]
    w = [[rng.randint(1, 10) for _ in range(m)] for _ in range(n)]
    home = [i % m for i in range(n)]
    base = [0] * m
    for i in range(n):
        base[home[i]] += w[i][home[i]]
    C = [base[j] + rng.randint(2, 12) for j in range(m)]
    return {"family": "gap", "n": n, "seed": seed, "m": m, "c": c, "w": w, "C": C}


def spec_knapsack(n, seed):
    rng = random.Random(seed)
    R = 2
    v = [rng.randint(1, 20) for _ in range(n)]
    w = [[rng.randint(1, 10) for _ in range(n)] for _ in range(R)]
    C = [max(1, int(0.5 * sum(w[r]))) for r in range(R)]
    return {"family": "knapsack", "n": n, "seed": seed, "R": R, "v": v, "w": w, "C": C}


# ---- gurobipy models (standard formulation, matching the PuLP encoding) ----
def build_gap(spec):
    n, m, c, w, C = spec["n"], spec["m"], spec["c"], spec["w"], spec["C"]
    md = gp.Model("gap")
    md.Params.OutputFlag = 0; md.Params.Threads = 1; md.Params.TimeLimit = TIMELIMIT
    md.Params.MIPGap = 0.0; md.Params.MIPGapAbs = 0.0  # prove TRUE optimum (no gap-tol early stop)
    x = md.addVars(n, m, vtype=GRB.BINARY)
    md.setObjective(gp.quicksum(c[i][j] * x[i, j] for i in range(n) for j in range(m)),
                    GRB.MINIMIZE)
    for i in range(n):
        md.addConstr(gp.quicksum(x[i, j] for j in range(m)) == 1)
    for j in range(m):
        md.addConstr(gp.quicksum(w[i][j] * x[i, j] for i in range(n)) <= C[j])
    return md, n * m


def build_knapsack(spec):
    n, R, v, w, C = spec["n"], spec["R"], spec["v"], spec["w"], spec["C"]
    md = gp.Model("knapsack")
    md.Params.OutputFlag = 0; md.Params.Threads = 1; md.Params.TimeLimit = TIMELIMIT
    md.Params.MIPGap = 0.0; md.Params.MIPGapAbs = 0.0  # prove TRUE optimum (no gap-tol early stop)
    x = md.addVars(n, vtype=GRB.BINARY)
    md.setObjective(gp.quicksum(v[i] * x[i] for i in range(n)), GRB.MAXIMIZE)
    for r in range(R):
        md.addConstr(gp.quicksum(w[r][i] * x[i] for i in range(n)) <= C[r])
    return md, n


_BUILD = {"gap": (spec_gap, build_gap), "knapsack": (spec_knapsack, build_knapsack)}


def run_one(family, n, seed):
    spec_fn, build_fn = _BUILD[family]
    spec = spec_fn(n, seed)
    md, nvars = build_fn(spec)                 # model construction: NOT timed
    t0 = time.perf_counter()
    md.optimize()                             # solve: timed
    solve_s = time.perf_counter() - t0
    proved = md.Status == GRB.OPTIMAL
    obj = md.ObjVal if md.SolCount > 0 else None
    return {"family": family, "n": n, "seed": seed, "nvars": nvars,
            "solve_s": round(solve_s, 3), "proved_optimal": proved,
            "objective": None if obj is None else round(obj, 3),
            "exceeds_restricted_cap": nvars > RESTRICTED_CAP}


def main():
    # confirm we actually have the FULL (non-restricted) license
    try:
        env = gp.Env(empty=True); env.start()
        gp.Model(env=env)  # would raise if no usable license
    except gp.GurobiError as e:
        print(f"!! Gurobi license problem: {e}")
        print("   Set GRB_LICENSE_FILE to the node-locked gurobi.lic and retry.")
        raise

    out = os.path.join(REPO, "runs", "gurobi_win")
    os.makedirs(out, exist_ok=True)
    rows = []
    print(f"Gurobi {gp.gurobi.version()}  (TimeLimit={TIMELIMIT:.0f}s, single-thread)\n")
    print(f"{'family':10}{'n':>6}{'nvars':>8}{'solve_s':>9}  {'status':8}{'obj':>12}  cap")
    for family, sizes in SIZES.items():
        for n in sizes:
            for seed in SEEDS:
                r = run_one(family, n, seed)
                rows.append(r)
                st = "OPT" if r["proved_optimal"] else "T/O*"
                cap = ">2000" if r["exceeds_restricted_cap"] else "ok"
                print(f"{family:10}{n:>6}{r['nvars']:>8}{r['solve_s']:>9.3f}  "
                      f"{st:8}{str(r['objective']):>12}  {cap}")
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)

    # per-(family,size) median solve time, for the paper
    import statistics as st
    agg = {}
    for r in rows:
        agg.setdefault((r["family"], r["n"]), []).append(r["solve_s"])
    print("\n=== median solve time (full Gurobi) ===")
    for (fam, n), ts in agg.items():
        nv = next(r["nvars"] for r in rows if r["family"] == fam and r["n"] == n)
        flag = "  (> restricted 2000-var cap: full license required)" if nv > RESTRICTED_CAP else ""
        print(f"  {fam:10} n={n:<5} nvars={nv:<7} median={st.median(ts):.3f}s{flag}")
    print(f"\nWrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
