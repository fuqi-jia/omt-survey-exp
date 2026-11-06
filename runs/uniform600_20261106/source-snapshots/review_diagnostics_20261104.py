#!/usr/bin/env python3
"""Targeted diagnostics for the 2026-11-02 survey review."""

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/review_diagnostics_20261104"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optimathsat():
    import _optimathsat
    sys.modules.setdefault("_mathsat", _optimathsat)
    import optimathsat as ms

    status_names = {
        ms.MSAT_OPT_UNKNOWN: "UNKNOWN",
        ms.MSAT_OPT_UNSAT: "UNSAT",
        ms.MSAT_OPT_SAT_PARTIAL: "SAT_PARTIAL",
        ms.MSAT_OPT_SAT_APPROX: "SAT_APPROX",
        ms.MSAT_OPT_SAT_OPTIMAL: "SAT_OPTIMAL",
    }
    fields = [
        ("optimum", ms.MSAT_OPTIMUM),
        ("final_lower", ms.MSAT_FINAL_LOWER),
        ("final_upper", ms.MSAT_FINAL_UPPER),
        ("final_error", ms.MSAT_FINAL_ERROR),
    ]
    originals = {
        "C1_inf_unattained": ROOT / "runs/nra_20261030/optimathsat/C1_inf_unattained.smt2",
        "A_r5": ROOT / "runs/nra_irrational_20261102/optimathsat/A_r5/input.smt2",
    }
    references = {
        "C1_inf_unattained": {"exact": "sqrt(2), not attained", "numeric": math.sqrt(2)},
        "A_r5": {"exact": "(3*sqrt(7)-sqrt(3))/2", "numeric": (3 * math.sqrt(7) - math.sqrt(3)) / 2},
    }
    for case in originals:
        started = time.monotonic()
        cfg = ms.msat_create_default_config("QF_NRA")
        ms.msat_set_option(cfg, "model_generation", "true")
        env = ms.msat_create_opt_env(cfg)
        ms.msat_destroy_config(cfg)
        real = ms.msat_get_rational_type(env)

        def var(name):
            decl = ms.msat_declare_function(env, name, real)
            return ms.msat_make_constant(env, decl)

        def num(value):
            return ms.msat_make_number(env, str(value))

        def ge(left, right):
            return ms.msat_make_leq(env, right, left)

        x = var("x")
        zero = num(0)
        if case == "C1_inf_unattained":
            constraints = [
                ms.msat_make_not(env, ms.msat_make_leq(env, x, zero)),
                ms.msat_make_not(env, ms.msat_make_leq(env, ms.msat_make_times(env, x, x), num(2))),
            ]
            objective = x
            variables = [("x", x)]
        else:
            y = var("y")
            five = num(5)
            constraints = [
                ge(x, zero), ge(five, x), ge(y, zero), ge(five, y),
                ge(ms.msat_make_times(env, x, y), num(1)),
                ge(ms.msat_make_plus(env, ms.msat_make_times(env, x, x),
                                      ms.msat_make_times(env, y, y)), five),
            ]
            objective = ms.msat_make_plus(env, x, ms.msat_make_times(env, num(2), y))
            variables = [("x", x), ("y", y)]
        for formula in constraints:
            assert ms.msat_assert_formula(env, formula) == 0
        obj = ms.msat_make_minimize(env, objective)
        assert ms.msat_assert_objective(env, obj) == 0
        solve_result = int(ms.msat_solve(env))
        result = int(ms.msat_objective_result(env, obj))
        inf = var("diagnostic_inf")
        eps = var("diagnostic_eps")
        values = {}
        for name, field in fields:
            term = ms.msat_objective_value_term(env, obj, field, inf, eps)
            values[name] = {
                "term": ms.msat_term_repr(term),
                "epsilon": int(ms.msat_objective_value_get_epsilon(env, obj, field)),
                "unbounded": int(ms.msat_objective_value_is_unbounded(env, obj, field)),
            }
        model_load = int(ms.msat_load_objective_model(env, obj))
        model = None
        candidate_objective = None
        if model_load == 0:
            model = {name: ms.msat_term_repr(ms.msat_get_model_value(env, term))
                     for name, term in variables}
            candidate_objective = ms.msat_term_repr(ms.msat_get_model_value(env, objective))
        record = {
            "case": case,
            "construction": "original constraints rebuilt through the OptiMathSAT 1.7.4 Python API; C1 uses strict x*x > 2",
            "asserted_formulas": [ms.msat_term_repr(f) for f in constraints],
            "original_cli_input": str(originals[case].relative_to(ROOT)),
            "original_cli_sha256": sha256(originals[case]),
            "solve_result": solve_result,
            "objective_status_code": result,
            "objective_status": status_names[result],
            "values": values,
            "model_load_result": model_load,
            "model": model,
            "candidate_objective": candidate_objective,
            "independent_reference": references[case],
            "elapsed_s": time.monotonic() - started,
        }
        save(OUT / "optimathsat" / (case + ".json"), record)
        print(case, record["objective_status"], values["optimum"], model, flush=True)
        ms.msat_destroy_opt_env(env)


def couenne():
    import pyomo.environ as p
    from pyomo.common.tempfiles import TempfileManager
    import nra_irrational_20261102 as irrational
    import nra_public_20261102 as common

    name = "C_r29_5"
    model = json.loads((irrational.OUT / "models" / (name + ".json")).read_text())
    folder = OUT / "couenne" / name
    folder.mkdir(parents=True, exist_ok=True)
    TempfileManager.tempdir = str(folder)
    m = irrational.pyomo_model(model)
    m.x[0].fix(1)
    m.x[1].fix(2)
    opt = p.SolverFactory("couenne", executable=common.SOLVERS["couenne"])
    opt.options.update({"bonmin.time_limit": 120, "bonmin.allowable_gap": 1e-8,
                        "bonmin.allowable_fraction_gap": 1e-8})
    started = time.monotonic()
    result = opt.solve(m, tee=False, keepfiles=True, load_solutions=False,
                       logfile=str(folder / "solver.log"))
    x = None
    if len(result.solution):
        m.solutions.load_from(result)
        x = [p.value(m.x[0]), p.value(m.x[1])]
    original_nl = irrational.OUT / "couenne" / name / "tmpco28k909.pyomo.nl"
    record = {
        "case": name,
        "fixed_variables": {"x": 1, "y": 2},
        "expected_witness_branch": 1,
        "exact_witness_checks": {
            "xy": 2, "xy_at_least_1": True,
            "x_squared_plus_y_squared": 5, "second_radius_at_least_5": True,
            "x_at_most_1": True, "bounds_0_to_7": True,
        },
        "solver_status": str(result.solver.status),
        "termination_condition": str(result.solver.termination_condition),
        "returned_x": x,
        "returned_objective": p.value(m.obj),
        "original_nl": str(original_nl.relative_to(ROOT)),
        "original_nl_sha256": sha256(original_nl),
        "elapsed_s": time.monotonic() - started,
    }
    save(folder / "result.json", record)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def hilbert():
    import gurobipy as gp
    from gurobipy import GRB

    n = 10
    H = [[Fraction(1, i + j + 1) for j in range(n)] for i in range(n)]
    b = [sum(row) for row in H]
    folder = OUT / "hilbert"
    folder.mkdir(parents=True, exist_ok=True)
    m = gp.Model("hilbert_n10_review")
    m.Params.OutputFlag = 1
    m.Params.LogFile = str(folder / "gurobi.log")
    m.Params.Threads = 1
    m.Params.TimeLimit = 120
    x = [m.addVar(0, 2, vtype=GRB.INTEGER, name=f"x{j}") for j in range(n)]
    for i in range(n):
        m.addConstr(gp.quicksum(float(H[i][j]) * x[j] for j in range(n)) == float(b[i]))
    m.optimize()
    raw = [v.X for v in x] if m.SolCount else None
    rounded = [round(v) for v in raw] if raw is not None else None
    exact_residual = None
    double_residual = None
    if rounded is not None:
        exact_residual = max(abs(sum(H[i][j] * rounded[j] for j in range(n)) - b[i])
                             for i in range(n))
        double_residual = max(abs(sum(float(H[i][j]) * rounded[j] for j in range(n)) - float(b[i]))
                              for i in range(n))
    best = None
    best_vector = None
    ones = (1,) * n
    for vector in itertools.product(range(3), repeat=n):
        if vector == ones:
            continue
        residual = max(abs(sum(H[i][j] * vector[j] for j in range(n)) - b[i])
                       for i in range(n))
        if best is None or residual < best:
            best, best_vector = residual, vector
    m.write(str(folder / "floating-input.lp"))
    record = {
        "n": n,
        "solver_version": list(gp.gurobi.version()),
        "status_code": int(m.Status),
        "is_optimal_status": m.Status == GRB.OPTIMAL,
        "solution_count": m.SolCount,
        "raw_vector": raw,
        "rounded_vector": rounded,
        "rounded_vector_is_ones": rounded == list(ones),
        "exact_residual_at_rounded_vector": str(exact_residual),
        "exact_residual_at_rounded_vector_float": float(exact_residual) if exact_residual is not None else None,
        "double_input_residual_at_rounded_vector": double_residual,
        "enumeration": {
            "vectors_checked": 3 ** n - 1,
            "minimum_nonunit_exact_infinity_residual": str(best),
            "minimum_nonunit_exact_infinity_residual_float": float(best),
            "witness": list(best_vector),
        },
    }
    save(folder / "result.json", record)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def fp():
    import re

    cases = []
    nan_records = []
    zero_records = []
    for path in sorted((ROOT / "runs/public_fp_full_20261030/cases").glob("[0-9][0-9][0-9][0-9].json")):
        case = json.loads(path.read_text())
        cases.append(case)
        routes = case["routes"]
        if routes["fp"]["status"] == "nan":
            nan_records.append({"index": case["index"], "group": case["group"],
                                "statuses": {name: rec["status"] for name, rec in routes.items()}})
        zeros = {}
        for form, rec in routes.items():
            if rec["status"] != "verified":
                continue
            value = rec.get("verification", {}).get("value")
            if form == "fp":
                match = re.fullmatch(r"\(fp #b([01]) #b([01]+) #b([01]+)\)", str(value))
                if match and not int(match.group(2)) and not int(match.group(3)):
                    zeros[form] = "-0" if match.group(1) == "1" else "+0"
            else:
                key = int(value)
                for width in (32, 64):
                    if key == 2 ** (width - 1):
                        zeros[form] = "+0"
                    elif key == 2 ** (width - 1) - 1:
                        zeros[form] = "-0"
        if zeros:
            zero_records.append({"index": case["index"], "group": case["group"], "verified_zeros": zeros})
    assert len(cases) == 1120
    assert len(nan_records) == 4
    assert all(rec["statuses"]["bvfp"] == rec["statuses"]["bv"] == "unsat" for rec in nan_records)
    shared_signs_agree = all(len(set(rec["verified_zeros"].values())) == 1 for rec in zero_records)
    assert shared_signs_agree
    report = {
        "population": len(cases),
        "nan_records": nan_records,
        "verified_zero_count": len(zero_records),
        "verified_zero_records": zero_records,
        "zero_signs_agree_across_completed_routes": shared_signs_agree,
        "scope": "outcome audit; not a claim that native FP and BV-key semantics are identical in general",
    }
    save(OUT / "fp/semantics-audit.json", report)
    print(json.dumps({"nan": len(nan_records), "verified_zero": len(zero_records),
                      "zero_signs_agree": shared_signs_agree}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["optimathsat", "couenne", "hilbert", "fp"])
    args = parser.parse_args()
    {"optimathsat": optimathsat, "couenne": couenne, "hilbert": hilbert, "fp": fp}[args.kind]()


if __name__ == "__main__":
    main()
