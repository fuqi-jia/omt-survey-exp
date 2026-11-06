#!/usr/bin/env python3
"""Check completeness, original reference points and every reported hit."""

from collections import Counter
import hashlib
import json
from pathlib import Path

from nra_public_20261102 import BENCH, OUT, ROOT, LIMIT, assess, save


def main():
    selection = json.loads((BENCH / "selection.json").read_text())
    names = {r["name"] for r in selection["selected"]}
    assert len(names) == 43
    solvers = ["z3", "ocac", "optimathsat", "ipopt", "couenne", "scipy", "gurobi"]
    records, references, table = [], [], {}
    for name in sorted(names):
        path = OUT / "models" / (name + ".json")
        model = json.loads(path.read_text())
        sol = BENCH / "reference-points" / (name + ".sol")
        values = {line.split()[0]: float(line.split()[1]) for line in sol.read_text().splitlines() if line.strip()}
        reference = assess(model, [values.get(v["name"], 0.0) for v in model["variables"]], model["reference"])
        assert reference["reference_hit"], (name, reference)
        references.append(dict(instance=name, **reference))
        for solver in solvers:
            result = json.loads((OUT / solver / name / "result.json").read_text())
            assert result["solver"] == solver and result["instance"] == name
            assert result["status"] != "WORKER_ERROR", (solver, name)
            if result.get("model_sha256"):
                assert result["model_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            if result.get("candidate_source"):
                folder = OUT / solver / name
                assert result["candidate_sha256"] == hashlib.sha256((folder / result["candidate_source"]).read_bytes()).hexdigest()
                assert json.loads((folder / "solver-run.json").read_text())["status"] == "ERROR"
                assert result["nl_column_mapping_verified"]
            checked = assess(model, result.get("x"), model["reference"])
            assert checked["feasible"] == result["feasible"]
            assert checked["reference_hit"] == result["reference_hit"]
            assert result["elapsed_s"] <= LIMIT + 46, (solver, name, result["elapsed_s"])
            records.append(result)
            if solver not in table:
                table[solver] = {str(i): 0 for i in range(2, 6)}
            table[solver][str(len(model["variables"]))] += int(result["reference_hit"])
    assert len(records) == 301
    for solver in solvers:
        assert len([r for r in records if r["solver"] == solver]) == 43
    save(OUT / "reference-encoding-audit.json", dict(passed=True, records=references))
    save(OUT / "table.json", table)
    save(OUT / "delivery-audit.json", dict(passed=True, total_calls=len(records),
         solver_counts=dict(Counter(r["solver"] for r in records)),
         table=table, reference_points_verified=len(references)))
    print(json.dumps(table, indent=2))
    print("PASS: 301 calls, all 43 reference encodings and every reported recovery")


if __name__ == "__main__":
    main()
