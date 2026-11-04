#!/usr/bin/env python3
"""Shared polynomial encodings for the complete, preselected MINLPLib cohort.

Selection precedes solver runs. Original OSiL decimal coefficients are retained
as rational numbers in SMT and converted to doubles only by numerical backends.
All candidate vectors are re-evaluated against the shared polynomial model.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import queue
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks/minlplib-qcqp-20261102"
OUT = ROOT / "runs/nra_public_20261102"
LIMIT = 120
SOLVERS = {
    "z3": "/tmp/gomt-z3-5.3.3/bin/z3",
    "ocac": str(ROOT / "tools/local-nra-20261028/cvc5-ocac"),
    "optimathsat": str(ROOT / "tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat"),
    "ipopt": "/tmp/gomt-nlp-20261102/bin/ipopt",
    "couenne": "/tmp/gomt-nlp-20261102/bin/couenne",
}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def expand(element):
    result = []
    for el in element:
        value, inc = Fraction(el.text), Fraction(el.get("incr", "0"))
        result.extend(value + j * inc for j in range(int(el.get("mult", "1"))))
    return result


def read_osil(path):
    tree = ET.parse(path).getroot()
    for node in tree.iter():
        node.tag = node.tag.split("}")[-1]
    data = tree.find("instanceData")
    variables = [dict(name=v.get("name"), lb=v.get("lb", "0"), ub=v.get("ub", "INF"))
                 for v in data.find("variables")]
    cons = [dict(lb=c.get("lb", "-INF"), ub=c.get("ub", "INF"), terms=[], constant="0")
            for c in data.find("constraints")]
    o = data.find("objectives/obj")
    obj = dict(terms=[], constant=o.get("constant", "0"))
    for c in o:
        obj["terms"].append([c.text, [int(c.get("idx"))]])
    linear = data.find("linearConstraintCoefficients")
    if linear is not None:
        starts, values = [int(x) for x in expand(linear.find("start"))], expand(linear.find("value"))
        assert len(values) == int(linear.get("numberOfValues"))
        if linear.find("colIdx") is not None:
            indices = [int(x) for x in expand(linear.find("colIdx"))]
            assert len(starts) == len(cons) + 1
            for i in range(len(cons)):
                for k in range(starts[i], starts[i + 1]):
                    cons[i]["terms"].append([str(values[k]), [indices[k]]])
        else:
            indices = [int(x) for x in expand(linear.find("rowIdx"))]
            assert len(starts) == len(variables) + 1
            for j in range(len(variables)):
                for k in range(starts[j], starts[j + 1]):
                    cons[indices[k]]["terms"].append([str(values[k]), [j]])
    for q in data.findall("quadraticCoefficients/qTerm"):
        idx = int(q.get("idx"))
        target = obj if idx == -1 else cons[idx]
        target["terms"].append([q.get("coef"), [int(q.get("idxOne")), int(q.get("idxTwo"))]])
    assert data.find("nonlinearExpressions") is None
    return dict(name=path.stem, variables=variables, constraints=cons, objective=obj,
                sense=o.get("maxOrMin"), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def number(text):
    if text.upper() in ("INF", "+INF", "-INF"):
        return float(text.replace("INF", "inf"))
    return float(Fraction(text))


def evaluate(poly, x):
    return number(poly["constant"]) + sum(number(c) * math.prod(x[j] for j in ids)
                                          for c, ids in poly["terms"])


def assess(model, x, reference):
    if x is None or len(x) != len(model["variables"]) or not all(math.isfinite(v) for v in x):
        return dict(feasible=False, reference_hit=False, objective=None)
    absolute, scaled = 0.0, 0.0
    for value, var in zip(x, model["variables"]):
        for b, direction in ((number(var["lb"]), -1), (number(var["ub"]), 1)):
            if math.isfinite(b):
                violation = max(0.0, direction * (value - b))
                absolute = max(absolute, violation)
                scaled = max(scaled, violation / max(1.0, abs(b)))
    for con in model["constraints"]:
        value = evaluate(con, x)
        for b, direction in ((number(con["lb"]), -1), (number(con["ub"]), 1)):
            if math.isfinite(b):
                violation = max(0.0, direction * (value - b))
                absolute = max(absolute, violation)
                scaled = max(scaled, violation / max(1.0, abs(b)))
    objective = evaluate(model["objective"], x)
    error = abs(objective - reference) / max(1.0, abs(reference))
    return dict(objective=objective, feasible=scaled <= 1e-6,
                reference_hit=scaled <= 1e-6 and error <= 1e-6,
                max_absolute_violation=absolute, max_scaled_violation=scaled,
                relative_reference_error=error)


def smt_number(s):
    f = Fraction(s)
    num = str(abs(f.numerator))
    if f.denominator != 1:
        num = f"(/ {num} {f.denominator})"
    return f"(- {num})" if f < 0 else num


def smt_poly(poly):
    terms = [smt_number(poly["constant"])]
    terms += ["(* " + " ".join([smt_number(c)] + [f"x{j}" for j in ids]) + ")"
              for c, ids in poly["terms"]]
    return "(+ " + " ".join(terms) + ")"


def smt_source(model, solver):
    lines = ["(set-option :produce-models true)"]
    if solver == "z3":
        lines += ["(set-option :pp.decimal true)", "(set-option :pp.decimal_precision 20)"]
    lines += ["(set-logic " + ("OMT_QF_NRA" if solver == "ocac" else "QF_NRA") + ")"]
    for i, v in enumerate(model["variables"]):
        lines.append(f"(declare-fun x{i} () Real)")
        for key, op in (("lb", ">="), ("ub", "<=")):
            if math.isfinite(number(v[key])):
                lines.append(f"(assert ({op} x{i} {smt_number(v[key])}))")
    for con in model["constraints"]:
        for key, op in (("lb", ">="), ("ub", "<=")):
            if math.isfinite(number(con[key])):
                lines.append(f"(assert ({op} {smt_poly(con)} {smt_number(con[key])}))")
    lines += ["(declare-fun obj () Real)",
              f"(assert (= obj {smt_poly(model['objective'])}))",
              f"({'minimize' if model['sense']=='min' else 'maximize'} (+ obj 0))",
              "(check-sat)", "(get-objectives)"]
    if solver != "ocac":
        lines.append("(get-value (" + " ".join(f"x{i}" for i in range(len(model["variables"]))) + "))")
    return "\n".join(lines) + "\n"


def sexprs(text):
    tokens = re.findall(r'\(|\)|\|[^|]*\||"(?:[^"]|"")*"|[^\s()]+', text)
    stack, roots = [], []
    for t in tokens:
        if t == "(":
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif t == ")":
            if stack:
                stack.pop()
        else:
            (stack[-1] if stack else roots).append(t)
    return roots


def smt_value(node):
    if isinstance(node, str):
        return float(Fraction(node.rstrip("?")))
    op, *a = node
    values = [smt_value(v) for v in a]
    if op == "-":
        return -values[0] if len(values) == 1 else values[0] - values[1]
    if op == "/":
        return values[0] / values[1]
    if op == "+":
        return sum(values)
    if op == "*":
        return math.prod(values)
    raise ValueError("Unsupported model numeral: " + repr(node))


def parse_vector(stdout, n):
    for node in reversed(sexprs(stdout)):
        if isinstance(node, list) and node and all(isinstance(t, list) and len(t) == 2 for t in node):
            values = {pair[0]: pair[1] for pair in node if isinstance(pair[0], str)}
            if all(f"x{i}" in values for i in range(n)):
                return [smt_value(values[f"x{i}"]) for i in range(n)]
    return None


def load_z3():
    # Match the manuscript's Z3 version in independent witness checks, too.
    sys.path.insert(0, "/tmp/gomt-z3-5.3.3/python")
    import z3
    assert z3.get_version_string() == "5.3.3"
    return z3


def z3_float(value):
    if hasattr(value, "approx"):
        value = value.approx(30)
    return value.numerator_as_long() / value.denominator_as_long()


def reported_objective(stdout):
    algebraics = {}
    def algebraic(match):
        z3 = load_z3()
        poly, lo, hi = match.groups()
        var = z3.Real("algebraic_root")
        terms = poly.replace(" ", "").replace("(", "").replace(")", "").split("+")
        expr = 0
        for term in terms:
            m = re.fullmatch(r"(-?\d+)(?:\*x(?:\^(\d+))?)?", term)
            if not m:
                raise ValueError("Unrecognized algebraic polynomial term: " + term)
            coeff, power = m.groups()
            degree = int(power) if power else 1 if "x" in term else 0
            expr += z3.RealVal(coeff) * var**degree
        s = z3.Solver()
        s.set(timeout=10000)
        s.add(expr == 0, var > z3.RealVal(lo), var < z3.RealVal(hi))
        if s.check() != z3.sat:
            raise ValueError("Cannot refine solver's isolated algebraic root")
        token = "ALGEBRAIC" + str(len(algebraics))
        algebraics[token] = z3_float(s.model().eval(var))
        return token
    text = re.sub(r"\(_ real_algebraic_number <(.*?), \(([^,]+), ([^)]+)\)>\)", algebraic, stdout)
    for node in sexprs(text):
        if isinstance(node, list) and len(node) >= 2 and node[0] == "objectives":
            value = node[1][-1]
            if isinstance(value, str) and value in algebraics:
                return algebraics[value]
            return smt_value(value)
    return None


def recover_witness(model, value):
    """Obtain a vector at the returned value when an OMT interface omits it.

    This is a satisfiability check at the solver's value, not another optimizer.
    The public reference value is not used in this query.
    """
    z3 = load_z3()
    text = re.split(r"\((?:minimize|maximize) ", smt_source(model, "z3"))[0]
    s = z3.Solver()
    s.set(timeout=30000)
    s.add(z3.parse_smt2_string(text))
    eps = 1e-8 * max(1.0, abs(value))
    obj = z3.Real("obj")
    s.add(obj >= z3.RealVal(repr(value - eps)), obj <= z3.RealVal(repr(value + eps)))
    if s.check() != z3.sat:
        return None
    m = s.model()
    return [z3_float(m.eval(z3.Real(f"x{i}"), model_completion=True))
            for i in range(len(model["variables"]))]


def starting_point(model):
    # Same deterministic, reference-independent start for all numerical solvers.
    x = []
    for var in model["variables"]:
        lb, ub = number(var["lb"]), number(var["ub"])
        x.append((lb + ub) / 2 if math.isfinite(lb) and math.isfinite(ub)
                 else max(0.0, lb) if math.isfinite(lb)
                 else min(0.0, ub) if math.isfinite(ub) else 0.0)
    return x


def pyomo_model(model, start=None):
    import pyomo.environ as p
    m = p.ConcreteModel()
    n = len(model["variables"])
    start = start or starting_point(model)
    bounds = [(None if not math.isfinite(number(v["lb"])) else number(v["lb"]),
               None if not math.isfinite(number(v["ub"])) else number(v["ub"]))
              for v in model["variables"]]
    m.x = p.Var(range(n), bounds=lambda m, i: bounds[i], initialize=lambda m, i: start[i])
    def expression(poly):
        return number(poly["constant"]) + sum(number(c) * math.prod(m.x[j] for j in ids)
                                              for c, ids in poly["terms"])
    m.obj = p.Objective(expr=expression(model["objective"]), sense=p.minimize if model["sense"] == "min" else p.maximize)
    m.cons = p.ConstraintList()
    for c in model["constraints"]:
        e, lb, ub = expression(c), number(c["lb"]), number(c["ub"])
        m.cons.add((None if not math.isfinite(lb) else lb, e, None if not math.isfinite(ub) else ub))
    return m


def worker(solver, name, core):
    if core is not None:
        os.sched_setaffinity(0, {core})
    # Enforced on the worker and inherited by its solver process.
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    model = json.loads((OUT / "models" / (name + ".json")).read_text())
    reference = model["reference"]
    folder = OUT / solver / name
    folder.mkdir(parents=True, exist_ok=True)
    x, status, stdout, stderr, parse_error = None, "ERROR", "", "", None
    started = time.monotonic()
    solver_elapsed, check_elapsed, reported = None, 0.0, None
    if solver in ("z3", "ocac", "optimathsat"):
        source = smt_source(model, solver)
        (folder / "input.smt2").write_text(source)
        cmd = [SOLVERS[solver]] + (["-optimization=TRUE"] if solver == "optimathsat" else []) + [str(folder / "input.smt2")]
        started = time.monotonic()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=LIMIT)
            stdout, stderr = result.stdout, result.stderr
            status = "RETURNED" if result.returncode == 0 else "ERROR"
            solver_elapsed = time.monotonic() - started
            check_start = time.monotonic()
            try:
                x = parse_vector(stdout, len(model["variables"]))
                reported = reported_objective(stdout)
                if x is None and reported is not None and math.isfinite(reported):
                    x = recover_witness(model, reported)
            except (ValueError, TypeError, ZeroDivisionError) as exc:
                parse_error = str(exc)
            check_elapsed = time.monotonic() - check_start
        except subprocess.TimeoutExpired as exc:
            status = "TIMEOUT"
            stdout = (exc.stdout or b"").decode(errors="replace")
            stderr = (exc.stderr or b"").decode(errors="replace")
    elif solver in ("ipopt", "couenne"):
        import pyomo.environ as p
        m = pyomo_model(model)
        opt = p.SolverFactory(solver, executable=SOLVERS[solver])
        if solver == "ipopt":
            opt.options.update(dict(max_cpu_time=LIMIT, tol=1e-8, constr_viol_tol=1e-8, bound_relax_factor=0))
        else:
            opt.options.update(dict(time_limit=LIMIT, allowable_gap=1e-8, allowable_fraction_gap=1e-8))
        from pyomo.common.tempfiles import TempfileManager
        TempfileManager.tempdir = str(folder)
        started = time.monotonic()
        try:
            result = opt.solve(m, tee=False, keepfiles=True, load_solutions=False, logfile=str(folder / "solver.log"))
            status = str(result.solver.termination_condition)
            if len(result.solution):
                m.solutions.load_from(result)
                x = [p.value(m.x[i]) for i in range(len(model["variables"]))]
        except Exception as exc:
            stderr = repr(exc)
    elif solver == "scipy":
        from scipy.optimize import minimize
        bounds = [(None if not math.isfinite(number(v["lb"])) else number(v["lb"]),
                   None if not math.isfinite(number(v["ub"])) else number(v["ub"]))
                  for v in model["variables"]]
        cons = []
        for c in model["constraints"]:
            lb, ub = number(c["lb"]), number(c["ub"])
            if lb == ub:
                cons.append(dict(type="eq", fun=lambda x, c=c, b=lb: evaluate(c, x) - b))
            else:
                if math.isfinite(lb):
                    cons.append(dict(type="ineq", fun=lambda x, c=c, b=lb: evaluate(c, x) - b))
                if math.isfinite(ub):
                    cons.append(dict(type="ineq", fun=lambda x, c=c, b=ub: b - evaluate(c, x)))
        started = time.monotonic()
        def callback(x):
            if time.monotonic() - started > LIMIT:
                raise TimeoutError("wall-clock limit")
        try:
            sign = 1 if model["sense"] == "min" else -1
            result = minimize(lambda x: sign * evaluate(model["objective"], x), starting_point(model),
                              bounds=bounds, constraints=cons, method="SLSQP", callback=callback,
                              options=dict(maxiter=10000, ftol=1e-8))
            x = result.x.tolist()
            status = "SUCCESS" if result.success else "FAILED: " + str(result.message)
            stdout = str(result)
        except TimeoutError:
            status = "TIMEOUT"
    else:
        raise ValueError(solver)
    elapsed = solver_elapsed if solver_elapsed is not None else time.monotonic() - started
    (folder / "stdout.txt").write_text(stdout)
    (folder / "stderr.txt").write_text(stderr)
    record = dict(solver=solver, instance=name, status=status, elapsed_s=elapsed,
                  timeout_s=LIMIT, core=core, x=x, parse_error=parse_error,
                  reported_objective=reported, witness_check_s=check_elapsed,
                  model_sha256=hashlib.sha256((OUT / "models" / (name + ".json")).read_bytes()).hexdigest(),
                  **assess(model, x, reference))
    save(folder / "result.json", record)
    print(solver, name, status, record["reference_hit"], round(elapsed, 3), flush=True)


def prepare():
    selection = json.loads((BENCH / "selection.json").read_text())
    for row in selection["selected"]:
        path = BENCH / (row["name"] + ".osil")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        m = read_osil(path)
        assert len(m["variables"]) == int(row["nvars"])
        assert len(m["constraints"]) == int(row["ncons"])
        m["reference"] = float(row["primalbound"])
        save(OUT / "models" / (m["name"] + ".json"), m)
    save(OUT / "protocol.json", dict(selection=selection, timeout_s=LIMIT, memory_gb=4, threads=1,
         starting_point="midpoint of two finite bounds; zero projected to one-sided bounds otherwise",
         feasibility="max(bound/constraint violation / max(1, absolute relevant bound)) <= 1e-6",
         reference_hit="feasible and abs(f-reference)/max(1,abs(reference)) <= 1e-6",
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def batch(solvers, cores, names=None):
    models = sorted(p.stem for p in (OUT / "models").glob("*.json"))
    if names:
        models = [n for n in models if n in names]
    # Round-robin per solver avoids a solver-specific wall-clock priority.
    jobs = [(s, n) for n in models for s in solvers if not (OUT / s / n / "result.json").exists()]
    tasks = queue.Queue()
    for job in jobs:
        tasks.put(job)
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               VECLIB_MAXIMUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
    def group(core):
        while True:
            try:
                solver, name = tasks.get_nowait()
            except queue.Empty:
                return
            folder = OUT / solver / name
            folder.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", solver, name,
                   "--core", str(core), "--output", str(OUT)]
            start = time.monotonic()
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, env=env, start_new_session=True)
                try:
                    output, errors = proc.communicate(timeout=LIMIT + 45)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate()
                    raise
                (folder / "worker.stdout").write_text(output)
                (folder / "worker.stderr").write_text(errors)
                if not (folder / "result.json").exists():
                    save(folder / "result.json", dict(solver=solver, instance=name, status="WORKER_ERROR",
                         elapsed_s=time.monotonic()-start, feasible=False, reference_hit=False,
                         objective=None, stderr=errors))
                print(output.strip()[-240:] or f"{solver} {name} WORKER_ERROR", flush=True)
            except subprocess.TimeoutExpired as exc:
                # Kill the solver subprocess as well as its Python wrapper.
                # Numerical backends have their own CPU limits; the outer cap
                # also catches a non-returning interface.
                save(folder / "result.json", dict(solver=solver, instance=name, status="TIMEOUT",
                     elapsed_s=time.monotonic()-start, feasible=False, reference_hit=False, objective=None))
                print(solver, name, "TIMEOUT", flush=True)
    with ThreadPoolExecutor(len(cores)) as pool:
        list(pool.map(group, cores))


def summary():
    records = [json.loads(p.read_text()) for p in OUT.glob("*/*/result.json")]
    records.sort(key=lambda r: (r["solver"], r["instance"]))
    save(OUT / "results.json", records)
    from collections import Counter
    report = {}
    for solver in sorted({r["solver"] for r in records}):
        rows = [r for r in records if r["solver"] == solver]
        report[solver] = dict(total=len(rows), feasible=sum(r["feasible"] for r in rows),
                              reference_hits=sum(r["reference_hit"] for r in rows),
                              statuses=dict(Counter(r["status"] for r in rows)))
    save(OUT / "summary.json", report)
    print(json.dumps(report, indent=2))


def main():
    global OUT
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--solvers", nargs="+")
    p.add_argument("--names", nargs="+")
    p.add_argument("--worker", nargs=2)
    p.add_argument("--core", type=int)
    p.add_argument("--cores", nargs="+", type=int, default=[0, 2, 4, 6, 8, 10])
    p.add_argument("--summary", action="store_true")
    p.add_argument("--output", default=str(OUT.relative_to(ROOT)))
    a = p.parse_args()
    OUT = ROOT / a.output
    if a.prepare:
        prepare()
    if a.worker:
        worker(*a.worker, a.core)
    if a.solvers:
        batch(a.solvers, a.cores, a.names)
    if a.summary:
        summary()


if __name__ == "__main__":
    main()
