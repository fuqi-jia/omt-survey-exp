#!/usr/bin/env python3
"""Generate the benchmark suite for one experiment config.

Reads a YAML config (families -> sizes, #seeds) and, for every instance, builds
the single structured spec and emits the equivalent encodings:

  smt2/<name>.smt2   OMT  (all families)
  lp/<name>.lp       MILP (PuLP writeLP, archival; runner rebuilds the model)
  mzn/<name>.mzn     CP   (Gecode/Chuffed)

CP-SAT has no on-disk artifact (it is an in-process model rebuilt from the spec).
A manifest.json records every instance and which paradigms apply -- it is the
single source of truth the runner consumes.

Output goes to  runs/<config-name>/  .

Usage:
  python scripts/gen_benchmarks.py --config configs/wsl.yaml
"""

import _bootstrap  # noqa: F401
import argparse
import json
import os

import yaml

from experiments.benchmarks.families import FAMILIES, build
from experiments.encodings.smt2 import to_smt2
from experiments.encodings.minizinc import to_minizinc, CP_FAMILIES
from experiments.encodings.milp import to_pulp, MILP_FAMILIES

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_dir(cfg_name: str) -> str:
    return os.path.join(REPO, "runs", cfg_name)


def generate(cfg: dict) -> dict:
    name = cfg["name"]
    seeds = int(cfg.get("seeds", 3))
    out = run_dir(name)
    for d in ("smt2", "lp", "mzn"):
        os.makedirs(os.path.join(out, d), exist_ok=True)

    manifest = []
    for family, sizes in cfg["families"].items():
        meta = FAMILIES[family]
        for size in sizes:
            for seed in range(seeds):
                spec = build(family, size, seed)
                iname = f"{meta.category}_{family}_{size}_{seed}"
                entry = {
                    "name": iname, "family": family, "category": meta.category,
                    "size": size, "seed": seed, "sense": meta.sense,
                    "paradigms": list(meta.paradigms),
                }
                # OMT (always)
                with open(os.path.join(out, "smt2", f"{iname}.smt2"), "w") as f:
                    f.write(to_smt2(spec))
                entry["smt2"] = f"smt2/{iname}.smt2"
                # MILP (archival .lp)
                if family in MILP_FAMILIES:
                    to_pulp(spec).writeLP(os.path.join(out, "lp", f"{iname}.lp"))
                    entry["lp"] = f"lp/{iname}.lp"
                # CP (.mzn)
                if family in CP_FAMILIES:
                    with open(os.path.join(out, "mzn", f"{iname}.mzn"), "w") as f:
                        f.write(to_minizinc(spec))
                    entry["mzn"] = f"mzn/{iname}.mzn"
                manifest.append(entry)

    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump({"config": cfg, "instances": manifest}, f, indent=1)
    return {"out": out, "n": len(manifest), "manifest": manifest}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path to a YAML config")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    res = generate(cfg)
    by_cat = {}
    for e in res["manifest"]:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    print(f"Generated {res['n']} instances -> {os.path.relpath(res['out'], REPO)}/")
    for c in sorted(by_cat):
        print(f"  category {c}: {by_cat[c]}")


if __name__ == "__main__":
    main()
