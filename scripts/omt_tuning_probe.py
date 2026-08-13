#!/usr/bin/env python3
"""Does tuning the OMT search strategy close the gap to MILP on the linear families?

Context: on the pure-linear families (§8 tab:exp-sep) OMT trails MILP by orders of
magnitude at the larger sizes. A fair reading of that result has to rule out the
obvious objection -- "you ran the OMT solvers on defaults". This probe therefore
sweeps the *documented* optimization-search knobs on the two sizes where the gap
is already wide, and reports whether any setting moves the needle by >=10x.

Solvers and knobs (names verified against the shipped --help, not assumed):
  OptiMathSAT 1.7.4  -opt.strategy = lin | bin | ada     (linear/binary/adaptive;
                     the DEFAULT is bin, not lin. Note the manual's caveat: bin
                     and ada want a lower bound on the objective to minimize.)
  Z3 4.15.4 (nuZ)    opt.optsmt_engine = basic | symba   (the only substantive
                     single-objective engine switch; opt.priority only selects
                     how MULTIPLE objectives combine (lex/box/pareto) and is
                     inert here, so it is reported as "n/a" rather than faked.)

Instances are NOT regenerated: it reuses the very SMT-LIB2 files the main
long600 run consumed (runs/long600/smt2/), so the probe and the table it argues
about are byte-identical inputs. Timeout, thread count and the optimality
criterion come from the shared adapter, so a "proved optimal" here means exactly
what it means in the main table.

Usage:
    .venv-cplex/bin/python scripts/omt_tuning_probe.py            # 600 s, 3 seeds
    .venv-cplex/bin/python scripts/omt_tuning_probe.py --timeout 60 --seeds 1
"""

import _bootstrap  # noqa: F401  (puts the repo root on sys.path)
import argparse
import json
import os
import statistics
import time

from experiments.benchmarks.families import build
from experiments.solvers import _sense
from experiments.solvers.omt import OptiMathSATSolver, Z3Solver

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SMT2_DIR = os.path.join(REPO, "runs", "long600", "smt2")

# (family, size, instance-name prefix) -- the two sizes where the OMT/MILP gap is
# already an order of magnitude in tab:exp-sep
TARGETS = [("gap", 160, "A_gap"), ("setcover", 240, "B_setcover")]


class TunedOptiMathSAT(OptiMathSATSolver):
    """OptiMathSAT with one extra command-line knob; everything else inherited."""

    def __init__(self, sense_lookup, flags, label):
        super().__init__(sense_lookup)
        self._flags = flags
        self.name = label

    def _cmd(self, smt2_path, timeout):
        return [self._binary(), "-optimization=TRUE", *self._flags, smt2_path]


class TunedZ3(Z3Solver):
    def __init__(self, sense_lookup, flags, label):
        super().__init__(sense_lookup)
        self._flags = flags
        self.name = label

    def _cmd(self, smt2_path, timeout):
        return ["z3", f"-T:{max(1, int(timeout))}", *self._flags, smt2_path]


def configs():
    out = [("optimathsat/default(bin)", TunedOptiMathSAT(_sense, [], "oms-default"))]
    for s in ("lin", "bin", "ada"):
        out.append((f"optimathsat/-opt.strategy={s}",
                    TunedOptiMathSAT(_sense, [f"-opt.strategy={s}"], f"oms-{s}")))
    out.append(("z3/default(basic)", TunedZ3(_sense, [], "z3-default")))
    out.append(("z3/opt.optsmt_engine=symba",
                TunedZ3(_sense, ["opt.optsmt_engine=symba"], "z3-symba")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    out_dir = os.path.join(REPO, "runs", "omt_tuning")
    os.makedirs(out_dir, exist_ok=True)
    jsonl = os.path.join(out_dir, "results.jsonl")
    done = set()
    if args.resume and os.path.exists(jsonl):
        for line in open(jsonl):
            try:
                r = json.loads(line)
                done.add((r["config"], r["name"]))
            except Exception:
                pass

    todo = [(fam, size, f"{pref}_{size}_{seed}", seed)
            for fam, size, pref in TARGETS for seed in range(args.seeds)]
    cfgs = configs()
    print(f"timeout={args.timeout}s  seeds={args.seeds}  "
          f"{len(cfgs)} configs x {len(todo)} instances\n")

    t0 = time.time()
    with open(jsonl, "a") as jf:
        for label, solver in cfgs:
            for fam, size, name, seed in todo:
                if (label, name) in done:
                    continue
                smt2 = os.path.join(SMT2_DIR, f"{name}.smt2")
                if not os.path.exists(smt2):
                    print(f"  !! missing {smt2}")
                    continue
                spec = build(fam, size, seed)
                res = solver.solve(spec, {"smt2": smt2}, args.timeout)
                rec = json.loads(res.to_json())
                rec.update({"config": label, "name": name, "family": fam,
                            "size": size, "seed": seed})
                jf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                jf.flush()
                print(f"  {label:<32}{name:<22}{rec.get('status'):<8}"
                      f"obj={rec.get('objective')} {rec.get('runtime_s', 0):.2f}s"
                      f"   [{(time.time()-t0)/60:.1f}m]")

    summarize(jsonl, out_dir)


def summarize(jsonl, out_dir):
    rows = [json.loads(l) for l in open(jsonl)]
    by = {}
    for r in rows:
        by.setdefault((r["family"], r["size"], r["config"]), []).append(r)
    lines = []
    for (fam, size), _ in {(f, s): 1 for f, s, _ in TARGETS}.items():
        lines.append(f"\n=== {fam} n={size} ===")
        lines.append(f"  {'config':<34}{'median s':>10}{'proved':>9}   per-seed")
        for key in sorted(k for k in by if k[0] == fam and k[1] == size):
            rs = sorted(by[key], key=lambda r: int(r["seed"]))
            # SAME convention as scripts/make_jobshop_table.py: a run that did not
            # prove optimality is ranked +inf, then take the median. Collapsing to
            # T/O whenever ANY seed failed would hide a finite median (2 of 3 seeds
            # proved still has a real middle value) and overstate the failure.
            vals = [float(x["runtime_s"]) if x.get("proved_optimal") else float("inf")
                    for x in rs]
            ok = sum(1 for v in vals if v != float("inf"))
            med = statistics.median(vals)
            per = " / ".join("T/O" if v == float("inf") else f"{v:.1f}" for v in vals)
            lines.append(f"  {key[2]:<34}"
                         f"{('T/O' if med == float('inf') else f'{med:.2f}'):>10}"
                         f"{f'{ok}/{len(rs)}':>9}   {per}")
    text = "\n".join(lines)
    print(text)
    open(os.path.join(out_dir, "summary.txt"), "w").write(text + "\n")
    print(f"\nWrote {os.path.relpath(out_dir, REPO)}/results.jsonl + summary.txt")


if __name__ == "__main__":
    main()
