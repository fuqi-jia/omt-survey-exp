#!/usr/bin/env python3
"""Re-run the Gurobi column of a config's matrix on WINDOWS under the FULL license.

Why this exists
---------------
Gurobi's full license here is NODE-locked to the Windows host, so in WSL2 the
`gurobipy` wheel falls back to the size-limited license and ERRORs out on any
model above ~2000 variables -- exactly the large instances that carry the
scalability argument (see DATA_PROVENANCE.md section 5).

Unlike `gurobi_linear_windows.py` (which inlines its own spec builders, a 30 s
timeout, one seed and three families, and therefore CANNOT be口径-matched to a
long-timeout run), this script **imports the very same adapter and spec builders
the WSL harness uses**:

    experiments.benchmarks.families.build   -> byte-identical instances (same seed)
    experiments.solvers.milp_indicator      -> the same native-API model

so the only difference from the WSL run is the license. That is the whole point:
the Gurobi column must differ from its WSL counterpart in licence alone, never in
encoding, timeout, seed set or instance data.

This is importable on Windows because the Unix-only `resource` module is used
only by `scripts/run_all.py`, not by the `experiments` package (psutil is
imported lazily and is installed into .venv-win).

Differences from the WSL harness, recorded honestly:
  * no per-solve subprocess isolation and no RLIMIT_AS memory cap (both Unix
    mechanisms). Gurobi is stable and these models are small, so neither
    materially applies; memory_peak_mb is still sampled via psutil.

Output: runs/<config>/gurobi_win/results.jsonl in the SAME record schema as the
main harness, ready to be merged into the main results.

Usage (from WSL):
    powershell.exe -NoProfile -Command "$env:GRB_LICENSE_FILE='...\gurobi.lic'; \
        & '...\.venv-win\Scripts\python.exe' scripts\gurobi_long600_windows.py --config configs\long600.yaml"
"""

import _bootstrap  # noqa: F401  (puts the repo root on sys.path)
import argparse
import json
import os
import sys
import time

import yaml

from experiments.benchmarks.families import build
from experiments.solvers.milp_indicator import GurobiIndicatorSolver

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as f:
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
                    help="override the config timeout (default: use it)")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    out_root = os.path.join(REPO, "runs", cfg["name"])
    manifest = json.load(open(os.path.join(out_root, "manifest.json")))["instances"]
    timeout = args.timeout if args.timeout is not None else float(cfg.get("timeout", 60))

    # --- fail loudly if we are NOT on the full license: a silent fallback to the
    # --- size-limited licence would quietly reproduce the very hole we are filling.
    import gurobipy as gp
    env = gp.Env(empty=True)
    env.start()
    probe = gp.Model(env=env)
    probe.addVars(4000, vtype="B")
    probe.update()
    print(f"Gurobi {gp.gurobi.version()}  full-license probe OK "
          f"({probe.NumVars} vars, restricted cap is 2000)")
    print(f"GRB_LICENSE_FILE = {os.environ.get('GRB_LICENSE_FILE', '<unset>')}")

    solver = GurobiIndicatorSolver()
    out_dir = os.path.join(out_root, "gurobi_win")
    os.makedirs(out_dir, exist_ok=True)
    jsonl = os.path.join(out_dir, "results.jsonl")
    done = load_done(jsonl) if args.resume else set()

    todo = [e for e in manifest
            if solver.paradigm in e["paradigms"]
            and solver.applies_to(e["family"])
            and (e["name"], solver.name) not in done]
    print(f"Config    : {cfg['name']} (timeout={timeout}s, {len(manifest)} instances)")
    print(f"Runs to do: {len(todo)}  (solver={solver.name})\n")

    t_start = time.time()
    with open(jsonl, "a") as jf:
        for i, e in enumerate(todo, 1):
            spec = build(e["family"], e["size"], e["seed"])
            res = solver.solve(spec, {}, timeout)
            rec = json.loads(res.to_json())
            # parent-known identity wins, exactly as run_all.py does
            rec.update({"name": e["name"], "family": e["family"],
                        "category": e["category"], "size": e["size"],
                        "seed": e["seed"], "paradigm": solver.paradigm,
                        "solver": solver.name})
            jf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            jf.flush()
            eta = (time.time() - t_start) / i * (len(todo) - i)
            print(f"  [{i:>3}/{len(todo)}] {e['name']:<22} {rec.get('status'):<8} "
                  f"obj={rec.get('objective')} {rec.get('runtime_s', 0):.3f}s "
                  f"ETA {eta/60:.1f}m")

    print(f"\nWrote {os.path.relpath(jsonl, REPO)}")


if __name__ == "__main__":
    sys.exit(main())
