#!/usr/bin/env python3
"""Run every available solver over a generated benchmark suite (serial, isolated).

Each (instance, solver) solve runs in its OWN subprocess (``--solve-one``) with a
memory cap and wall-clock timeout. This isolates native-solver crashes (a
SIGABRT in one backend can no longer kill the whole run -- it is recorded as
ERROR and the run continues) and frees memory between solves. Runs are serial
(no parallelism). Results stream to results.jsonl (resumable) and are then
consolidated to results.csv / results.json with a correctness cross-check.

Usage:
  python scripts/run_all.py --config configs/wsl.yaml --timeout 30 --memgb 4
  python scripts/run_all.py --config configs/full.yaml --resume
  python scripts/run_all.py --config configs/wsl.yaml --solvers z3,cbc,gecode
"""

import _bootstrap  # noqa: F401
import argparse
import csv
import json
import os
import subprocess
import sys
import time

import yaml

from experiments.benchmarks.families import build, FAMILIES
from experiments.solvers import detect_solvers, make_solver

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULT_MARK = "__RESULT__"

CSV_FIELDS = [
    "name", "family", "category", "size", "seed", "paradigm", "solver",
    "status", "proved_optimal", "objective", "runtime_s", "memory_peak_mb",
    "best_at_10s", "best_at_30s", "best_at_60s", "timeout_s",
]


# =====================================================================
# Worker mode: solve ONE (instance, solver) in this isolated process
# =====================================================================
def _limit_memory(gb):
    if not gb or gb <= 0:
        return
    try:
        import resource
        nbytes = int(gb * 1024 ** 3)
        resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
    except Exception:
        pass


def solve_one(args):
    _limit_memory(args.memgb)  # cap before any heavy native lib loads
    files = {}
    if args.smt2:
        files["smt2"] = args.smt2
    if args.mzn:
        files["mzn"] = args.mzn
    spec = build(args.family, args.size, args.seed)
    solver = make_solver(args.solver)
    res = solver.solve(spec, files, args.timeout)
    sys.stdout.write(RESULT_MARK + res.to_json() + "\n")
    sys.stdout.flush()


# =====================================================================
# Parent mode
# =====================================================================
def _base_record(e, s):
    return {"name": e["name"], "family": e["family"], "category": e["category"],
            "size": e["size"], "seed": e["seed"], "paradigm": s.paradigm,
            "solver": s.name}


def run_one_isolated(e, s, files, timeout, memgb, grace=30.0):
    """Spawn a subprocess to solve one (instance, solver); return a record dict.

    A worker crash (non-zero exit, e.g. SIGABRT) -> ERROR; a hang past
    timeout+grace -> TIMEOUT. Neither can take down the parent run.
    """
    rec = _base_record(e, s)
    cmd = [sys.executable, os.path.abspath(__file__), "--solve-one",
           "--solver", s.name, "--family", e["family"],
           "--size", str(e["size"]), "--seed", str(e["seed"]),
           "--timeout", str(timeout), "--memgb", str(memgb)]
    if "smt2" in files:
        cmd += ["--smt2", files["smt2"]]
    if "mzn" in files:
        cmd += ["--mzn", files["mzn"]]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout + grace)
    except subprocess.TimeoutExpired:
        rec.update(status="TIMEOUT", proved_optimal=False, objective=None,
                   runtime_s=round(time.perf_counter() - t0, 3),
                   memory_peak_mb=0.0, timeout_s=timeout,
                   error_message="worker wall-clock timeout")
        return rec
    if p.returncode != 0:
        tail = (p.stderr or p.stdout or "").strip()[-200:]
        rec.update(status="ERROR", proved_optimal=False, objective=None,
                   runtime_s=round(time.perf_counter() - t0, 3),
                   memory_peak_mb=0.0, timeout_s=timeout,
                   error_message=f"worker exit {p.returncode}: {tail}")
        return rec
    payload = None
    for line in p.stdout.splitlines():
        if line.startswith(RESULT_MARK):
            payload = json.loads(line[len(RESULT_MARK):])
    if payload is None:
        rec.update(status="ERROR", proved_optimal=False, objective=None,
                   runtime_s=round(time.perf_counter() - t0, 3),
                   memory_peak_mb=0.0, timeout_s=timeout,
                   error_message="no result from worker")
        return rec
    payload.update(rec)  # parent-known identity wins
    return payload


def main_run(args):
    cfg = yaml.safe_load(open(args.config))
    out = os.path.join(REPO, "runs", cfg["name"])
    manifest = json.load(open(os.path.join(out, "manifest.json")))["instances"]
    timeout = args.timeout if args.timeout is not None else float(cfg.get("timeout", 60))

    want = None if args.solvers == "all" else set(args.solvers.split(","))
    solvers = detect_solvers(want)
    print(f"Config         : {cfg['name']}  (timeout={timeout}s, mem={args.memgb}GB, "
          f"serial+isolated, {len(manifest)} instances)")
    print(f"Solvers        : {[s.name for s in solvers]}")

    jsonl = os.path.join(out, "results.jsonl")
    done = load_done(jsonl) if args.resume else set()
    if not args.resume and os.path.exists(jsonl):
        os.remove(jsonl)
    if done:
        print(f"Resuming       : {len(done)} (instance,solver) pairs already done")

    def applies(s, e):
        return (s.paradigm in e["paradigms"]
                and not (hasattr(s, "applies_to") and not s.applies_to(e["family"]))
                and (e["name"], s.name) not in done)

    total = sum(1 for e in manifest for s in solvers if applies(s, e))
    print(f"Runs to do     : {total}\n")

    t_start = time.time()
    n = 0
    with open(jsonl, "a") as jf:
        for e in manifest:
            files = {}
            for k in ("smt2", "lp", "mzn"):
                if k in e:
                    files[k] = os.path.join(out, e[k])
            for s in solvers:
                if not applies(s, e):
                    continue
                rec = run_one_isolated(e, s, files, timeout, args.memgb)
                jf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                jf.flush()
                n += 1
                eta = (time.time() - t_start) / n * (total - n) if n else 0
                print(f"  [{n:>4}/{total}] {e['name']:<22} {s.name:<12} "
                      f"{rec.get('status'):<8} obj={rec.get('objective')} "
                      f"{rec.get('runtime_s', 0):.3f}s "
                      f"mem={rec.get('memory_peak_mb', 0):.0f}MB  ETA {eta/60:.1f}m")

    consolidate_and_check(out, jsonl)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--timeout", type=float, default=None,
                    help="override per-call timeout (else from config)")
    ap.add_argument("--memgb", type=float, default=4.0,
                    help="per-solve memory cap in GB (subprocess RLIMIT_AS)")
    ap.add_argument("--solvers", default="all", help="comma list or 'all'")
    ap.add_argument("--resume", action="store_true",
                    help="skip (instance, solver) pairs already in results.jsonl")
    # worker mode
    ap.add_argument("--solve-one", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--solver")
    ap.add_argument("--family")
    ap.add_argument("--size", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--smt2")
    ap.add_argument("--mzn")
    args = ap.parse_args()

    if args.solve_one:
        if args.timeout is None:
            args.timeout = 60.0
        solve_one(args)
    else:
        if not args.config:
            ap.error("--config is required")
        main_run(args)


if __name__ == "__main__":
    main()
