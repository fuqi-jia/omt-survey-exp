#!/usr/bin/env python3
"""Run Gurobi against the shared, archived MINLPLib polynomial models."""

import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import gurobipy as gp
from gurobipy import GRB

from nra_public_20261102 import OUT, LIMIT, assess, number, save, starting_point


def main():
    import psutil
    psutil.Process().cpu_affinity([12])
    for path in sorted((OUT / "models").glob("*.json")):
        data = json.loads(path.read_text())
        name = data["name"]
        folder = OUT / "gurobi" / name
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / "result.json").exists():
            continue
        m = gp.Model()
        m.Params.Threads = 1
        m.Params.TimeLimit = LIMIT
        m.Params.MemLimit = 4
        m.Params.NonConvex = 2
        m.Params.MIPGap = 1e-8
        m.Params.MIPGapAbs = 1e-8
        m.Params.FeasibilityTol = 1e-8
        m.Params.OptimalityTol = 1e-8
        m.Params.LogFile = str(folder / "solver.log")
        variables = [m.addVar(lb=number(v["lb"]), ub=number(v["ub"]), name=f"x{i}")
                     for i, v in enumerate(data["variables"])]
        def expression(poly):
            result = gp.QuadExpr(number(poly["constant"]))
            for coeff, ids in poly["terms"]:
                term = number(coeff) * variables[ids[0]]
                if len(ids) == 2:
                    term *= variables[ids[1]]
                result += term
            return result
        for c in data["constraints"]:
            e, lb, ub = expression(c), number(c["lb"]), number(c["ub"])
            if lb == ub:
                m.addQConstr(e == lb)
            else:
                if lb != -float("inf"):
                    m.addQConstr(e >= lb)
                if ub != float("inf"):
                    m.addQConstr(e <= ub)
        m.setObjective(expression(data["objective"]), GRB.MINIMIZE if data["sense"] == "min" else GRB.MAXIMIZE)
        for v, start in zip(variables, starting_point(data)):
            v.Start = start
        started = time.monotonic()
        m.optimize()
        elapsed = time.monotonic() - started
        x = [v.X for v in variables] if m.SolCount else None
        save(folder / "result.json", dict(solver="gurobi", instance=name,
             status=str(m.Status), elapsed_s=elapsed, native_runtime=m.Runtime,
             objective_bound=m.ObjBound if m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else None,
             timeout_s=LIMIT, core=12, x=x, model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
             **assess(data, x, data["reference"])))
        print(name, m.Status, elapsed, flush=True)
        m.dispose()
    save(OUT / "gurobi-environment.json", dict(version=list(gp.gurobi.version()),
         python=sys.version, platform=platform.platform(),
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    main()
