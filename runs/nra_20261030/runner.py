#!/usr/bin/env python3
"""Run the six NRA examples locally and retain complete solver output."""

import argparse
import concurrent.futures
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import shutil
import time


REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools/local-nra-20261028"
OUT = REPO / "runs/nra_20261028"
TIMEOUT_S = 120
CASES = [
    ("A_sqrt2", "max", "(and (>= x 0) (<= (* x x) 2))"),
    ("A_sqrt5", "max", "(and (>= x 0) (<= (* x x) 5))"),
    ("B_5_9", "min", "(and (>= x 0) (<= x 5) (>= (* (- (* 2 x) 5) (- (* 2 x) 5)) 9))"),
    ("B_9_25", "min", "(and (>= x 0) (<= x 5) (>= (* (- (* 2 x) 9) (- (* 2 x) 9)) 25))"),
    ("C1_inf_unattained", "min", "(and (> x 0) (> (* x x) 2))"),
    ("C2_unbounded_below", "min", "(>= (* x x) 1)"),
]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def binary(solver):
    if solver == "z3":
        return Path(shutil.which("z3"))
    if solver == "ocac":
        return TOOLS / "cvc5-ocac"
    return REPO / "tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat"


def run_solver(job):
    solver, case = job
    name, direction, formula = case
    folder = OUT / solver
    folder.mkdir(exist_ok=True)
    logic = "OMT_QF_NRA" if solver == "ocac" else "QF_NRA"
    text = (f"(set-option :produce-models true)\n(set-logic {logic})\n"
            f"(declare-fun x () Real)\n(assert {formula})\n"
            f"({'maximize' if direction == 'max' else 'minimize'} (+ x 0))\n"
            "(check-sat)\n(get-objectives)\n")
    source = folder / (name + ".smt2")
    source.write_text(text)
    cmd = [str(binary(solver))]
    if solver == "optimathsat":
        cmd.append("-optimization=TRUE")
    cmd.append(str(source))
    env = dict(os.environ)
    
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=TIMEOUT_S)
        stdout, stderr, code, timed_out = proc.stdout, proc.stderr, proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        code, timed_out = None, True
    elapsed = time.monotonic() - started
    (folder / (name + ".stdout")).write_text(stdout)
    (folder / (name + ".stderr")).write_text(stderr)
    rec = {"solver": solver, "case": name, "command": cmd, "timeout_s": TIMEOUT_S,
           "elapsed_s": elapsed, "returncode": code, "timed_out": timed_out,
           "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
           "stdout": stdout, "stderr": stderr}
    print(solver, name, "timeout" if timed_out else stdout.strip().replace("\n", " "), flush=True)
    return rec


def scipy_results():
    import scipy
    from scipy.optimize import minimize
    results = []
    for name, direction, _ in CASES:
        starts = [5.0, 0.2] if name.startswith("B_") else [0.5 if direction == "max" else 5.0]
        for start in starts:
            bounds = [(0, None)] if name.startswith("A_") else [(0, 5)] if name.startswith("B_") else None
            if name.startswith("A_"):
                k = int(name[6:])
                cons = [{"type": "ineq", "fun": lambda v, k=k: k - v[0] ** 2}]
            elif name.startswith("B_"):
                a, b = map(int, name[2:].split("_"))
                cons = [{"type": "ineq", "fun": lambda v, a=a, b=b: (2*v[0]-a)**2-b}]
            else:
                k = 2 if name.startswith("C1") else 1
                cons = [{"type": "ineq", "fun": lambda v, k=k: v[0]**2-k}]
                if name.startswith("C1"):
                    cons.append({"type": "ineq", "fun": lambda v: v[0]})
            sign = -1 if direction == "max" else 1
            r = minimize(lambda v: sign*v[0], [start], bounds=bounds, constraints=cons, method="SLSQP")
            results.append({"case": name, "start": start, "x": float(r.x[0]),
                            "success": bool(r.success), "status": int(r.status),
                            "message": str(r.message), "constraints_at_x": [float(c["fun"](r.x)) for c in cons]})
    write_json(OUT / "scipy.json", {"version": scipy.__version__, "records": results})


GUROBI_CODE = r'''
import json, gurobipy as gp
from gurobipy import GRB
records = []
for name in ['A_sqrt2','A_sqrt5','B_5_9','B_9_25','C1_inf_unattained','C2_unbounded_below']:
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.TimeLimit=__TIMEOUT_S__
    m.Params.NonConvex=2;m.Params.DualReductions=0
    lower=0 if name.startswith(('A_','B_')) or name.startswith('C1') else -GRB.INFINITY
    upper=10 if name.startswith('A_') else 5 if name.startswith('B_') else GRB.INFINITY
    x=m.addVar(lb=lower,ub=upper)
    if name.startswith('A_'):m.addConstr(x*x<=int(name[6:]))
    elif name.startswith('B_'):
        a,b=map(int,name[2:].split('_'));m.addConstr((2*x-a)*(2*x-a)>=b)
    else:m.addConstr(x*x >= (2 if name.startswith('C1') else 1))
    m.setObjective(x,GRB.MAXIMIZE if name.startswith('A_') else GRB.MINIMIZE);m.optimize()
    records.append(dict(case=name,status=int(m.Status),x=x.X if m.SolCount else None,
                        objective=m.ObjVal if m.SolCount else None,runtime=m.Runtime))
print(json.dumps(dict(version=list(gp.gurobi.version()),records=records)))
'''


def main():
    global OUT, TIMEOUT_S
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=int)
    parser.add_argument("--solver", action="append", choices=["z3", "ocac", "optimathsat"])
    parser.add_argument("--numeric", action="store_true", help="SciPy numerical comparison only")
    parser.add_argument("--gurobi", action="store_true", help="author-run Gurobi comparison only")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", default="runs/nra_20261029")
    args = parser.parse_args()
    OUT = REPO / args.output
    TIMEOUT_S = args.timeout
    if args.core is not None:
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {args.core})
        else:
            import psutil
            psutil.Process().cpu_affinity([args.core])
    OUT.mkdir(parents=True, exist_ok=True)
    if args.numeric:
        scipy_results()
    if args.gurobi:
        env = dict(os.environ)
        code = GUROBI_CODE.replace("__TIMEOUT_S__", str(TIMEOUT_S))
        p = subprocess.run([sys.executable, "-c", code], env=env,
                           capture_output=True, text=True, timeout=6 * TIMEOUT_S + 5)
        (OUT / "gurobi.stdout").write_text(p.stdout)
        (OUT / "gurobi.stderr").write_text(p.stderr)
        if p.returncode:
            raise RuntimeError(p.stderr)
        write_json(OUT / "gurobi.json", json.loads(p.stdout.splitlines()[-1]))
    if args.gurobi and not args.solver:
        return
    solvers = args.solver or ["z3", "ocac", "optimathsat"]
    selected = {solver for solver in solvers}
    results_path = OUT / "results.json"
    old = json.loads(results_path.read_text()) if results_path.exists() else []
    records = [r for r in old if r["solver"] not in selected]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_solver, job) for job in [(s,c) for s in solvers for c in CASES]]
        for f in concurrent.futures.as_completed(futures):
            records.append(f.result())
            write_json(results_path, sorted(records, key=lambda r:(r["solver"],r["case"])))
    bins = {s: {"path": str(binary(s)), "sha256": hashlib.sha256(binary(s).read_bytes()).hexdigest()} for s in solvers}
    write_json(OUT / "environment.json", {"date": date.today().isoformat(), "python": sys.version,
               "platform": platform.platform(), "processors": platform.processor(),
               "solver_timeout_s": TIMEOUT_S, "binaries": bins,
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


if __name__ == "__main__":
    main()
