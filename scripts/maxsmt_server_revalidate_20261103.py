#!/usr/bin/env python3
"""Recheck a server CGM witness with an extended exact-validation budget."""
import argparse
import json
import os
from pathlib import Path
import time

import maxsmt_server_20261103 as server
import maxsmt_public_20261103 as experiment

RUN = server.experiment.RUN
TIMEOUT_MS = 300000


def validate(instance, config, stdout):
    declarations, _, _, _ = experiment.parse((RUN / "inputs" / instance / "original.smt2").read_text())
    query_costs = (["unsat_preferences", "unsat_requirements", "sat_tasks"]
                   if config.startswith("oms") else [f"__cgm_cost_{i}" for i in range(3)])
    names = [d[1] for d in declarations] + query_costs
    values = None
    for node in reversed(server.experiment.sexprs(stdout)):
        if isinstance(node, list) and len(node) == len(names):
            if all(isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str)
                   for pair in node):
                candidate = dict(node)
                if set(candidate) == set(names):
                    values = candidate
                    break
    assert values is not None, "missing complete model values"
    assignments = "\n".join(experiment.smt(["assert", ["=", name, values[name]]]) for name in names[:-3])
    assignments += "\n" + "\n".join(experiment.smt(["assert", ["=", f"__cgm_cost_{i}", values[name]]])
                                      for i, name in enumerate(query_costs))
    z3 = server.load_z3()
    solver = z3.Solver(ctx=z3.Context())
    solver.set(timeout=TIMEOUT_MS)
    solver.from_string((RUN / "inputs" / instance / "hard.smt2").read_text() + assignments)
    status = str(solver.check())
    objective = []
    if status == "sat":
        for name in names[-3:]:
            value = values[name]
            assert isinstance(value, str) and value.isdigit()
            objective.append(int(value))
    return status, objective


def main(instance, config, core):
    os.sched_setaffinity(0, {core})
    output = RUN / "results" / instance / config
    result_path = output / "result.json"
    original_bytes = result_path.read_bytes()
    row = json.loads(original_bytes)
    assert row["status"] == "invalid", row["status"]
    before = output / "result.before-revalidation.json"
    if not before.exists():
        before.write_bytes(original_bytes)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    begin = time.perf_counter()
    error = None
    try:
        status, objective = validate(instance, config, (output / "stdout.txt").read_text())
    except Exception as exc:
        status, objective, error = "error", [], str(exc)
    retry = dict(started=started, core=core, timeout_ms=TIMEOUT_MS,
                 elapsed_s=time.perf_counter() - begin, check=status, objective=objective,
                 previous_status=row["status"], previous_error=row.get("validation_error"), error=error)
    experiment.save(output / "validation_retry.json", retry)
    if status == "sat":
        row["status"] = "optimal"
        row["validation"] = dict(feasible=True, recomputed_costs=objective, check=status)
        row["objective"] = objective
        row.pop("validation_error", None)
        row["revalidation"] = retry
        experiment.save(result_path, row)
    print(json.dumps(dict(instance=instance, config=config, **retry), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("instance")
    parser.add_argument("config")
    parser.add_argument("core", type=int)
    arguments = parser.parse_args()
    main(arguments.instance, arguments.config, arguments.core)
