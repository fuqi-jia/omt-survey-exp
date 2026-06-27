#!/usr/bin/env python3
"""Full-CPLEX large-scale linear comparison (WSL, .venv-cplex).

Parallel to scripts/gurobi_linear_windows.py, but for the FULL CPLEX 22.1 that
runs in WSL via the .venv-cplex (Python 3.10) environment. Solves the pure-linear
and regular-logic families (gap, knapsack, config) across the separation table's
sizes (and larger), with MIPGap=0 so it proves the TRUE optimum (matching CBC and
the gap=0 Gurobi run, for a clean cross-check). Same instance data as the WSL
runs (spec builders copied verbatim from experiments/benchmarks/families.py).

  .venv-cplex/bin/python scripts/cplex_linear.py

Output: runs/cplex_lin/results.json + a printed table.
"""

import json
import os
import random
import time

from docplex.mp.model import Model

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIZES = {"gap": [80, 160, 320, 640],
         "config": [100, 200, 400, 800],
         "knapsack": [320, 640, 1280, 2560]}
SEEDS = [0]
TIMELIMIT = 30.0


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


def spec_config(n, seed):
    rng = random.Random(seed)
    cost = [rng.randint(5, 100) for _ in range(n)]
    perf = [rng.randint(1, 50) for _ in range(n)]
    deps = [(i, i + 1) for i in range(0, n - 1, 2)]
    mutex = [(i, min(i + 2, n - 1)) for i in range(0, n - 1, 5) if i + 2 < n]
    T = sum(perf) // 4
    return {"family": "config", "n": n, "seed": seed, "cost": cost,
            "perf": perf, "deps": deps, "mutex": mutex, "T": T}


def _new(name):
    m = Model(name)
    m.context.cplex_parameters.threads = 1
    m.parameters.timelimit = TIMELIMIT
    m.parameters.mip.tolerances.mipgap = 0.0
    m.parameters.mip.tolerances.absmipgap = 0.0
    return m


def build_gap(spec):
    n, mm, c, w, C = spec["n"], spec["m"], spec["c"], spec["w"], spec["C"]
    m = _new("gap")
    x = {(i, j): m.binary_var() for i in range(n) for j in range(mm)}
    m.minimize(m.sum(c[i][j] * x[i, j] for i in range(n) for j in range(mm)))
    for i in range(n):
        m.add(m.sum(x[i, j] for j in range(mm)) == 1)
    for j in range(mm):
        m.add(m.sum(w[i][j] * x[i, j] for i in range(n)) <= C[j])
    return m, n * mm


def build_knapsack(spec):
    n, R, v, w, C = spec["n"], spec["R"], spec["v"], spec["w"], spec["C"]
    m = _new("knapsack")
    x = [m.binary_var() for _ in range(n)]
    m.maximize(m.sum(v[i] * x[i] for i in range(n)))
    for r in range(R):
        m.add(m.sum(w[r][i] * x[i] for i in range(n)) <= C[r])
    return m, n


def build_config(spec):
    n, cost, perf = spec["n"], spec["cost"], spec["perf"]
    deps, mutex, T = spec["deps"], spec["mutex"], spec["T"]
    m = _new("config")
    sel = [m.binary_var() for _ in range(n)]
    m.minimize(m.sum(cost[i] * sel[i] for i in range(n)))
    m.add(m.sum(perf[i] * sel[i] for i in range(n)) >= T)
    for (i, j) in deps:
        m.add(sel[i] <= sel[j])
    for (i, j) in mutex:
        m.add(sel[i] + sel[j] <= 1)
    return m, n


_BUILD = {"gap": (spec_gap, build_gap), "knapsack": (spec_knapsack, build_knapsack),
          "config": (spec_config, build_config)}


def run_one(family, n, seed):
    spec_fn, build_fn = _BUILD[family]
    spec = spec_fn(n, seed)
    m, nvars = build_fn(spec)               # construction not timed
    t0 = time.perf_counter()
    sol = m.solve(log_output=False)         # solve timed
    solve_s = time.perf_counter() - t0
    status = m.solve_details.status if m.solve_details else "none"
    proved = sol is not None and "optimal" in status.lower()
    obj = sol.objective_value if sol is not None else None
    return {"family": family, "n": n, "seed": seed, "nvars": nvars,
            "solve_s": round(solve_s, 3), "proved_optimal": proved,
            "objective": None if obj is None else round(obj, 3)}


def main():
    out = os.path.join(REPO, "runs", "cplex_lin")
    os.makedirs(out, exist_ok=True)
    rows = []
    print(f"{'family':10}{'n':>6}{'nvars':>8}{'solve_s':>9}  {'status':8}{'obj':>12}")
    for family, sizes in SIZES.items():
        for n in sizes:
            for seed in SEEDS:
                r = run_one(family, n, seed)
                rows.append(r)
                st = "OPT" if r["proved_optimal"] else "T/O"
                print(f"{family:10}{n:>6}{r['nvars']:>8}{r['solve_s']:>9.3f}  "
                      f"{st:8}{str(r['objective']):>12}")
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)
    print(f"\nWrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
