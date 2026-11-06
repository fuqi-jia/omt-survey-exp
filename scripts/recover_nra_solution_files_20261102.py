#!/usr/bin/env python3
"""Read a solver-written solution when a native process exits abnormally.

The endpoint is a feasible vector at the independently known reference value,
not a successful exit code. The original process result and logs are retained.
A byte-identical reconstruction of the NL input verifies the column mapping.
No solver is rerun and no vector is repaired.
"""

import hashlib
import json
from pathlib import Path
import tempfile

import pyomo.environ as p
from pyomo.opt import ReaderFactory

import nra_public_20261102 as public
import nra_disjunctive_20261102 as logical


def main():
    manifest_path = public.OUT / "solution-file-recovery.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    for module in (public, logical):
        for path in sorted((module.OUT / "couenne").glob("*/result.json")):
            result = json.loads(path.read_text())
            if result["status"] != "ERROR":
                continue
            sol = list(path.parent.glob("*.sol"))
            inputs = list(path.parent.glob("*.nl"))
            if len(sol) != 1 or len(inputs) != 1:
                continue
            model = json.loads((module.OUT / "models" / (result["instance"] + ".json")).read_text())
            m = module.pyomo_model(model)
            with tempfile.TemporaryDirectory(prefix="gomt-nl-column-check-") as folder:
                regenerated, smap = m.write(str(Path(folder) / "input.nl"))
                assert Path(regenerated).read_bytes() == inputs[0].read_bytes(), result["instance"]
                try:
                    with ReaderFactory("sol") as reader:
                        solution = reader(str(sol[0]))
                    solution._smap_id = smap
                    m.solutions.load_from(solution)
                    x = [p.value(m.x[i]) for i in range(len(model["variables"]))]
                except Exception as exc:
                    manifest.append(dict(instance=result["instance"], recovered=False, error=repr(exc)))
                    continue
            (path.parent / "solver-run.json").write_bytes(path.read_bytes())
            result.update(native_status=result["status"], status="NATIVE_ERROR_WITH_SOLUTION",
                          x=x, candidate_source=sol[0].name,
                          candidate_sha256=hashlib.sha256(sol[0].read_bytes()).hexdigest(),
                          nl_column_mapping_verified=True,
                          **module.assess(model, x, model["reference"]))
            public.save(path, result)
            manifest.append(dict(instance=result["instance"], cohort=module.OUT.name,
                                 recovered=True, feasible=result["feasible"],
                                 reference_hit=result["reference_hit"]))
    manifest = list({(r.get("cohort"), r["instance"]): r for r in manifest}.values())
    public.save(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
