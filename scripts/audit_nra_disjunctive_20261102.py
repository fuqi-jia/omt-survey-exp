#!/usr/bin/env python3
"""Validate the complete logical/nonlinear cohort and exact references."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from nra_disjunctive_20261102 import OUT, BENCH, assess, summary
from nra_public_20261102 import LIMIT, save


def main():
    solvers = ["z3", "ocac", "optimathsat", "couenne", "gurobi"]
    rows = []
    for path in sorted((OUT / "models").glob("*.json")):
        model = json.loads(path.read_text())
        assert path.read_bytes() == (BENCH / path.name).read_bytes()
        ref = model["exact_reference"]
        assert ref["active_sets_enumerated"] == 2**model["n"]
        vector = [F(v) for v in ref["vector"]]
        assert sum(vector[1::2]) == F(ref["value"])
        assert sum(u["b"] * vector[2*i] for i, u in enumerate(model["units"])) >= model["demand"]
        for i, u in enumerate(model["units"]):
            x, z = vector[2*i:2*i+2]
            assert (x == z == 0) or (u["l"] <= x <= u["u"] and z == u["s"] + u["a"] * x*x)
        assert assess(model, list(map(float, vector)), model["reference"])["reference_hit"]
        for solver in solvers:
            result = json.loads((OUT / solver / model["name"] / "result.json").read_text())
            assert result["status"] != "WORKER_ERROR", (solver, model["name"])
            if result.get("model_sha256"):
                assert result["model_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            checked = assess(model, result.get("x"), model["reference"])
            assert checked["feasible"] == result["feasible"]
            assert checked["reference_hit"] == result["reference_hit"]
            assert result["elapsed_s"] <= LIMIT + 46
            rows.append(result)
    assert len(rows) == 45
    assert all(r["reference_hit"] for r in rows if r["solver"] == "gurobi")
    summary()
    save(OUT / "delivery-audit.json", dict(passed=True, total_calls=45, exact_references=9,
         complete_solver_matrix=True, all_reported_hits_rechecked=True))
    print("PASS: 45 calls, nine exact references and every reported recovery")


if __name__ == "__main__":
    main()
