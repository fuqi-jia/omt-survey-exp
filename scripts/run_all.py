#!/usr/bin/env python3
"""Run every available solver over a generated benchmark suite.

For each instance in runs/<config>/manifest.json we run each detected solver
whose paradigm the instance supports, recording a uniform SolverResult. Results
are streamed to results.jsonl (crash-resilient for long server runs) and then
consolidated into results.csv / results.json. Finally a correctness cross-check
verifies that all solvers proving optimality on the same instance agree on the
objective -- this is what validates that the four encodings are equivalent.

Usage:
  python scripts/run_all.py --config configs/wsl.yaml
  python scripts/run_all.py --config configs/full.yaml --resume
  python scripts/run_all.py --config configs/wsl.yaml --solvers z3,cbc,gecode
"""

import _bootstrap  # noqa: F401
import argparse
import csv
import json
import os
import time

import yaml

from experiments.benchmarks.families import build
from experiments.solvers import detect_solvers

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CSV_FIELDS = [
    "name", "family", "category", "size", "seed", "paradigm", "solver",
    "status", "proved_optimal", "objective", "runtime_s", "memory_peak_mb",
    "best_at_10s", "best_at_30s", "best_at_60s", "timeout_s",
]


def load_done(jsonl_path):
    done = set()
    if os.path.exists(jsonl_path):
        with open(jsonl_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["name"], r["solver"]))
                except Exception:
                    pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--timeout", type=float, default=None,
                    help="override per-call timeout (else from config)")
    ap.add_argument("--solvers", default="all",
                    help="comma list or 'all'")
    ap.add_argument("--resume", action="store_true",
                    help="skip (instance, solver) pairs already in results.jsonl")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    out = os.path.join(REPO, "runs", cfg["name"])
    manifest = json.load(open(os.path.join(out, "manifest.json")))["instances"]
    timeout = args.timeout if args.timeout is not None else float(cfg.get("timeout", 60))

    want = None if args.solvers == "all" else set(args.solvers.split(","))
    solvers = detect_solvers(want)
    print(f"Config         : {cfg['name']}  (timeout={timeout}s, {len(manifest)} instances)")
    print(f"Solvers        : {[s.name for s in solvers]}")

    jsonl = os.path.join(out, "results.jsonl")
    done = load_done(jsonl) if args.resume else set()
    if not args.resume and os.path.exists(jsonl):
        os.remove(jsonl)
    if done:
        print(f"Resuming       : {len(done)} (instance,solver) pairs already done")

    total = sum(1 for e in manifest for s in solvers
                if s.paradigm in e["paradigms"] and (e["name"], s.name) not in done)
    print(f"Runs to do     : {total}\n")

    t_start = time.time()
    n = 0
    with open(jsonl, "a") as jf:
        for e in manifest:
            files = {}
            for k in ("smt2", "lp", "mzn"):
                if k in e:
                    files[k] = os.path.join(out, e[k])
            spec = build(e["family"], e["size"], e["seed"])
            for s in solvers:
                if s.paradigm not in e["paradigms"]:
                    continue
                if (e["name"], s.name) in done:
                    continue
                res = s.solve(spec, files, timeout)
                # fill identity
                res.name = e["name"]
                res.family = e["family"]
                res.category = e["category"]
                res.instance = e["name"]
                res.size = e["size"]
                res.seed = e["seed"]
                d = res.to_dict()
                d["name"] = e["name"]
                d["solver"] = res.solver_name  # CSV/cross-check use short key
                jf.write(json.dumps(d, ensure_ascii=False) + "\n")
                jf.flush()
                n += 1
                obj = res.objective
                eta = (time.time() - t_start) / n * (total - n) if n else 0
                print(f"  [{n:>4}/{total}] {e['name']:<22} {s.name:<12} "
                      f"{res.status:<8} obj={obj} {res.runtime_s:.3f}s "
                      f"mem={res.memory_peak_mb:.0f}MB  ETA {eta/60:.1f}m")

    consolidate_and_check(out, jsonl)


def consolidate_and_check(out, jsonl):
    rows = []
    with open(jsonl) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    with open(os.path.join(out, "results.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False, default=str)

    # ---- correctness cross-check: proven optima must agree per instance ----
    print("\n=== correctness cross-check (proven optima must agree) ===")
    by_inst = {}
    for r in rows:
        if r.get("proved_optimal") and r.get("objective") is not None:
            by_inst.setdefault(r["name"], []).append((r["solver"], r["objective"]))
    mismatches, n_cross = 0, 0
    for name, lst in sorted(by_inst.items()):
        if len(lst) > 1:
            n_cross += 1
            if len({v for _, v in lst}) > 1:
                mismatches += 1
                print(f"  MISMATCH {name}: {lst}")
    if mismatches == 0:
        print(f"  OK: all {n_cross} multi-solver instances agree on the optimum.")
    else:
        print(f"  {mismatches} MISMATCH(es) -- encodings are NOT equivalent!")
    print(f"\nWrote results.csv / results.json ({len(rows)} runs) to "
          f"{os.path.relpath(out, REPO)}/")


if __name__ == "__main__":
    main()
