#!/usr/bin/env python3
"""Add IPOPT and Couenne to the six archived one-dimensional examples."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import time

from nra_public_20261102 import ROOT, SOLVERS, LIMIT, pyomo_model, save

OUT = ROOT / "runs/nra_numeric_extensions_20261102"


def cases():
    models = []
    for name in ("A_sqrt2", "A_sqrt5", "B_5_9", "B_9_25", "C1_inf_unattained", "C2_unbounded_below"):
        var = dict(name="x", lb="0" if not name.startswith("C2") else "-INF", ub="5" if name.startswith("B") else "INF")
        obj = dict(constant="0", terms=[["1", [0]]])
        if name.startswith("A"):
            con = dict(lb="-INF", ub=name[6:], constant="0", terms=[["1", [0, 0]]])
        elif name.startswith("B"):
            a, b = map(int, name[2:].split("_"))
            con = dict(lb="0", ub="INF", constant=str(a*a-b), terms=[["4", [0, 0]], [str(-4*a), [0]]])
        else:
            con = dict(lb="2" if name.startswith("C1") else "1", ub="INF", constant="0", terms=[["1", [0, 0]]])
        models.append(dict(name=name, variables=[var], constraints=[con], objective=obj,
                           sense="max" if name.startswith("A") else "min"))
    return models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True, choices=["ipopt", "couenne"])
    parser.add_argument("--core", type=int, default=14)
    args = parser.parse_args()
    os.sched_setaffinity(0, {args.core})
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    import pyomo.environ as p
    from pyomo.common.tempfiles import TempfileManager
    records = []
    for data in cases():
        starts = [5.0, 0.2] if data["name"].startswith("B") and args.solver == "ipopt" else [0.5 if data["sense"] == "max" else 5.0]
        for start in starts:
            folder = OUT / args.solver / (data["name"] + "_" + str(start))
            folder.mkdir(parents=True, exist_ok=True)
            TempfileManager.tempdir = str(folder)
            m = pyomo_model(data, [start])
            opt = p.SolverFactory(args.solver, executable=SOLVERS[args.solver])
            if args.solver == "ipopt":
                opt.options.update(dict(max_cpu_time=LIMIT, tol=1e-8, constr_viol_tol=1e-8, bound_relax_factor=0))
            else:
                opt.options.update({"bonmin.time_limit": LIMIT, "bonmin.allowable_gap": 1e-8,
                                    "bonmin.allowable_fraction_gap": 1e-8})
            begun = time.monotonic()
            result = opt.solve(m, tee=False, keepfiles=True, load_solutions=False, logfile=str(folder / "solver.log"))
            elapsed = time.monotonic() - begun
            x = None
            if len(result.solution):
                m.solutions.load_from(result)
                x = p.value(m.x[0])
            record = dict(case=data["name"], start=start, x=x, status=str(result.solver.termination_condition),
                          elapsed_s=elapsed, timeout_s=LIMIT, model=data)
            save(folder / "result.json", record)
            records.append(record)
            print(args.solver, data["name"], start, x, record["status"], flush=True)
    save(OUT / (args.solver + ".json"), dict(records=records,
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    main()
