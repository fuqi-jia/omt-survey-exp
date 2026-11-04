#!/usr/bin/env python3
"""Coupled disjunctive quadratic resource allocation, with exact references.

Each unit is off (x=z=0), or on (l<=x<=u and z>=s+a*x^2).
The shared demand couples the choices. M=s+a*u^2 bounds each cost variable.
For each active set the remaining convex quadratic problem is solved by exact
rational water filling. Exhaustive enumeration gives an independent optimum.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import random
import signal
import subprocess
import sys
import time

import nra_public_20261102 as base

ROOT = base.ROOT
OUT = ROOT / "runs/nra_disjunctive_20261102"
BENCH = ROOT / "benchmarks/nra-disjunctive-20261102"
ORIGINAL_SMT = base.smt_source
ORIGINAL_ASSESS = base.assess
ORIGINAL_PYOMO = base.pyomo_model


def active_solution(units, active, demand):
    if sum(units[i]["b"] * units[i]["u"] for i in active) < demand:
        return None
    if sum(units[i]["b"] * units[i]["l"] for i in active) >= demand:
        x = {i: F(units[i]["l"]) for i in active}
    else:
        def at(lam):
            return {i: min(F(units[i]["u"]), max(F(units[i]["l"]),
                         lam * F(units[i]["b"], 2 * units[i]["a"]))) for i in active}
        def amount(lam):
            return sum(units[i]["b"] * value for i, value in at(lam).items())
        points = sorted({F(2 * units[i]["a"] * units[i][key], units[i]["b"])
                         for i in active for key in ("l", "u")})
        lam = next((v for v in points if amount(v) == demand), None)
        if lam is None:
            for lo, hi in zip(points, points[1:]):
                if amount(lo) < demand < amount(hi):
                    mid, slope, constant = (lo + hi) / 2, F(0), F(0)
                    for i in active:
                        unit = units[i]
                        low, high = F(2*unit["a"]*unit["l"], unit["b"]), F(2*unit["a"]*unit["u"], unit["b"])
                        if mid <= low:
                            constant += unit["b"] * unit["l"]
                        elif mid >= high:
                            constant += unit["b"] * unit["u"]
                        else:
                            slope += F(unit["b"]**2, 2*unit["a"])
                    lam = (demand - constant) / slope
                    break
        assert lam is not None
        x = at(lam)
        assert sum(units[i]["b"] * value for i, value in x.items()) == demand
    cost = sum(F(units[i]["s"]) + units[i]["a"] * value**2 for i, value in x.items())
    return cost, x


def exact_reference(units, demand):
    best, best_x, best_mask = None, None, None
    feasible_sets = 0
    for mask in range(1 << len(units)):
        active = [i for i in range(len(units)) if mask >> i & 1]
        solution = active_solution(units, active, demand)
        if solution is None:
            continue
        feasible_sets += 1
        cost, x = solution
        if best is None or cost < best:
            best, best_x, best_mask = cost, x, mask
    vector = []
    for i, unit in enumerate(units):
        value = best_x.get(i, F(0))
        vector += [value, F(unit["s"]) + unit["a"] * value**2 if i in best_x else F(0)]
    return dict(value=str(best), vector=[str(v) for v in vector], active_mask=best_mask,
                active_sets_enumerated=1 << len(units), feasible_active_sets=feasible_sets)


def generate(n, seed):
    rng = random.Random(20261102 + 100*n + seed)
    units = []
    for i in range(n):
        l = rng.randint(1, 3)
        units.append(dict(l=l, u=l+rng.randint(2, 6), a=rng.randint(1, 5),
                          s=rng.randint(2, 15), b=rng.randint(1, 4)))
    demand = sum(u["b"]*u["u"] for u in units) * 45 // 100
    variables, objective, disjunctions = [], [], []
    for i, unit in enumerate(units):
        x, z = 2*i, 2*i+1
        cap = unit["s"] + unit["a"] * unit["u"]**2
        variables += [dict(name=f"x{i}", lb="0", ub=str(unit["u"])),
                      dict(name=f"z{i}", lb="0", ub=str(cap))]
        objective.append(["1", [z]])
        off = [dict(lb="0", ub="0", constant="0", terms=[["1", [j]]]) for j in (x, z)]
        on = [dict(lb=str(unit["l"]), ub="INF", constant="0", terms=[["1", [x]]]),
              dict(lb=str(unit["s"]), ub="INF", constant="0",
                   terms=[["1", [z]], [str(-unit["a"]), [x, x]]])]
        disjunctions.append([off, on])
    common = dict(lb=str(demand), ub="INF", constant="0", terms=[[str(u["b"]), [2*i]] for i, u in enumerate(units)])
    reference = exact_reference(units, demand)
    return dict(name=f"switch_n{n}_s{seed}", n=n, seed=seed, units=units, demand=demand,
                variables=variables, objective=dict(constant="0", terms=objective),
                constraints=[common], disjunctions=disjunctions, sense="min",
                reference=float(F(reference["value"])), exact_reference=reference)


def assess(model, x, reference):
    result = ORIGINAL_ASSESS(model, x, reference)
    if x is None:
        return result
    for branches in model["disjunctions"]:
        scores = []
        for branch in branches:
            scores.append(ORIGINAL_ASSESS(dict(model, constraints=branch), x, reference))
        chosen = min(scores, key=lambda r: r["max_scaled_violation"])
        result["max_scaled_violation"] = max(result["max_scaled_violation"], chosen["max_scaled_violation"])
        result["max_absolute_violation"] = max(result["max_absolute_violation"], chosen["max_absolute_violation"])
    result["feasible"] = result["max_scaled_violation"] <= 1e-6
    result["reference_hit"] = result["feasible"] and result["relative_reference_error"] <= 1e-6
    return result


def smt_source(model, solver):
    text = ORIGINAL_SMT(model, solver)
    assertions = []
    for branches in model["disjunctions"]:
        terms = []
        for branch in branches:
            conditions = []
            for con in branch:
                for key, op in (("lb", ">="), ("ub", "<=")):
                    if math.isfinite(base.number(con[key])):
                        conditions.append(f"({op} {base.smt_poly(con)} {base.smt_number(con[key])})")
            terms.append("(and " + " ".join(conditions) + ")")
        assertions.append("(assert (or " + " ".join(terms) + "))")
    return text.replace("(declare-fun obj", "\n".join(assertions) + "\n(declare-fun obj")


def pyomo_model(model, start=None):
    import pyomo.environ as p
    m = ORIGINAL_PYOMO(model, start)
    m.on = p.Var(range(model["n"]), domain=p.Binary, initialize=1)
    for i, u in enumerate(model["units"]):
        x, z, on = m.x[2*i], m.x[2*i+1], m.on[i]
        cap = u["s"] + u["a"] * u["u"]**2
        m.cons.add(x >= u["l"]*on)
        m.cons.add(x <= u["u"]*on)
        m.cons.add(z <= cap*on)
        m.cons.add(z >= u["s"]*on + u["a"]*x*x)
    return m


def prepare():
    for n in (4, 8, 12):
        for seed in range(3):
            model = generate(n, seed)
            vector = [float(F(v)) for v in model["exact_reference"]["vector"]]
            assert assess(model, vector, model["reference"])["reference_hit"]
            base.save(OUT / "models" / (model["name"] + ".json"), model)
            base.save(BENCH / (model["name"] + ".json"), model)
    base.save(OUT / "protocol.json", dict(sizes=[4, 8, 12], seeds=[0, 1, 2], timeout_s=120,
         memory_gb=4, threads=1, demand_fraction="floor(0.45 * total weighted capacity)",
         parameter_ranges=dict(l=[1, 3], u_minus_l=[2, 6], a=[1, 5], s=[2, 15], b=[1, 4]),
         reference="enumerate every active set; exact rational KKT/water-filling solution in each set",
         numeric_encoding="l*y<=x<=u*y; z<=M*y; z>=s*y+a*x^2; y binary, M=s+a*u^2",
         acceptance="same 1e-6 feasibility and reference-objective tolerances as MINLPLib cohort",
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def worker(solver, name, core):
    # Isolated-process adapters keep the original public-cohort runner unchanged.
    base.OUT = OUT
    base.smt_source, base.pyomo_model, base.assess = smt_source, pyomo_model, assess
    base.worker(solver, name, core)


def batch(solvers, cores):
    tasks = queue.Queue()
    for n in (4, 8, 12):
        for seed in range(3):
            name = f"switch_n{n}_s{seed}"
            for solver in solvers:
                if not (OUT / solver / name / "result.json").exists():
                    tasks.put((solver, name))
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    def group(core):
        while True:
            try:
                solver, name = tasks.get_nowait()
            except queue.Empty:
                return
            folder = OUT / solver / name
            folder.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", solver, name, "--core", str(core)]
            started = time.monotonic()
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env=env, start_new_session=True)
            try:
                stdout, stderr = proc.communicate(timeout=165)
                (folder / "worker.stdout").write_text(stdout)
                (folder / "worker.stderr").write_text(stderr)
                if not (folder / "result.json").exists():
                    base.save(folder / "result.json", dict(solver=solver, instance=name, status="WORKER_ERROR",
                         elapsed_s=time.monotonic()-started, feasible=False, reference_hit=False, objective=None))
                print(stdout.strip()[-200:] or f"{solver} {name} WORKER_ERROR", flush=True)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                base.save(folder / "result.json", dict(solver=solver, instance=name, status="TIMEOUT",
                     elapsed_s=time.monotonic()-started, feasible=False, reference_hit=False, objective=None))
                print(solver, name, "TIMEOUT", flush=True)
    with ThreadPoolExecutor(len(cores)) as pool:
        list(pool.map(group, cores))


def gurobi():
    import gurobipy as gp
    from gurobipy import GRB
    import psutil
    psutil.Process().cpu_affinity([12])
    for path in sorted((OUT / "models").glob("*.json")):
        data = json.loads(path.read_text())
        folder = OUT / "gurobi" / data["name"]
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / "result.json").exists():
            continue
        m = gp.Model()
        m.Params.Threads, m.Params.TimeLimit, m.Params.MemLimit = 1, 120, 4
        m.Params.MIPGap, m.Params.MIPGapAbs = 1e-8, 1e-8
        m.Params.FeasibilityTol, m.Params.OptimalityTol = 1e-8, 1e-8
        m.Params.LogFile = str(folder / "solver.log")
        x, z, on = [], [], []
        for i, u in enumerate(data["units"]):
            cap = u["s"] + u["a"]*u["u"]**2
            x.append(m.addVar(lb=0, ub=u["u"], name=f"x{i}"))
            z.append(m.addVar(lb=0, ub=cap, name=f"z{i}"))
            on.append(m.addVar(vtype=GRB.BINARY, name=f"on{i}"))
            m.addConstr(x[i] >= u["l"]*on[i])
            m.addConstr(x[i] <= u["u"]*on[i])
            m.addConstr(z[i] <= cap*on[i])
            m.addQConstr(z[i] >= u["s"]*on[i] + u["a"]*x[i]*x[i])
        m.addConstr(gp.quicksum(u["b"]*v for u, v in zip(data["units"], x)) >= data["demand"])
        m.setObjective(gp.quicksum(z), GRB.MINIMIZE)
        begun = time.monotonic()
        m.optimize()
        elapsed = time.monotonic()-begun
        vector = [value for pair in zip(x, z) for value in (pair[0].X, pair[1].X)] if m.SolCount else None
        base.save(folder / "result.json", dict(solver="gurobi", instance=data["name"],
             status=str(m.Status), elapsed_s=elapsed, timeout_s=120, core=12, x=vector,
             model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
             **assess(data, vector, data["reference"])))
        m.dispose()


def summary():
    from statistics import median
    rows = [json.loads(p.read_text()) for p in OUT.glob("*/*/result.json")]
    base.save(OUT / "results.json", rows)
    report = {}
    for solver in sorted({r["solver"] for r in rows}):
        report[solver] = {}
        for n in (4, 8, 12):
            selected = [r for r in rows if r["solver"] == solver and r["instance"].startswith(f"switch_n{n}_")]
            times = [r["elapsed_s"] if r["reference_hit"] else float("inf") for r in selected]
            mid = median(times) if times else float("inf")
            report[solver][str(n)] = dict(total=len(selected), hits=sum(r["reference_hit"] for r in selected),
                  median_s=mid if math.isfinite(mid) else None)
    base.save(OUT / "summary.json", report)
    print(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--worker", nargs=2)
    p.add_argument("--solvers", nargs="+")
    p.add_argument("--core", type=int)
    p.add_argument("--cores", nargs="+", type=int, default=[12, 14])
    p.add_argument("--gurobi", action="store_true")
    p.add_argument("--summary", action="store_true")
    a = p.parse_args()
    if a.prepare:
        prepare()
    if a.worker:
        worker(*a.worker, a.core)
    if a.solvers:
        batch(a.solvers, a.cores)
    if a.gurobi:
        gurobi()
    if a.summary:
        summary()


if __name__ == "__main__":
    main()
