#!/usr/bin/env python3
"""Emit the LaTeX body of the paper's job-shop table (tab:exp-jobshop).

Reviewer Major-18 asked for more than 3 seeds, because at n=9/10 the
seed-to-seed spread on this family is large enough that a 3-sample median
cannot support a *ranking* claim. This script therefore reports, per cell:

    median   over ALL seeds, with a non-proved run ranked as +inf
             (so a solver that fails on half its seeds reads "T/O", not a
             flattering median over only the runs it happened to finish)
    ^{k/K}   superscript, printed ONLY when k<K seeds were proved optimal

The superscript is what makes the table honest at a glance: "516.20" and
"516.20 with 3 of 10 proved" are very different claims, and the old
median-only table could not tell them apart.

min-max spread is NOT put in the table (11 solver columns x 2 extra numbers
would not fit the journal's page width); it is quoted in the prose for the
rows where it carries the argument, and `--spread` prints it here.

Usage:
    python scripts/make_jobshop_table.py --run jobshop_seeds
    python scripts/make_jobshop_table.py --run jobshop_seeds --seeds 7 --spread
"""

import argparse
import collections
import json
import os

INF = float("inf")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# (solver key, column header) in the paper's column order
COLS = [
    ("z3",          r"$\nu Z$"),
    ("optimathsat", "OptiM."),
    ("cbc-bigm",    "CBC"),
    ("highs-bigm",  "HiGHS"),
    ("scip-bigm",   "SCIP"),
    ("gurobi-bigm", "bigM"),
    ("gurobi-ind",  "ind"),
    ("cplex-bigm",  "bigM"),
    ("cplex-ind",   "ind"),
    ("gecode",      "Gec."),
    ("cpsat",       "CP-SAT"),
]


def median(vals):
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="jobshop_seeds")
    ap.add_argument("--seeds", type=int, default=None,
                    help="use seeds 0..K-1 only (default: every complete seed)")
    ap.add_argument("--spread", action="store_true",
                    help="also print min-max per cell, for quoting in the prose")
    args = ap.parse_args()

    path = os.path.join(REPO, "runs", args.run, "results.jsonl")
    rows = [json.loads(l) for l in open(path)]

    # a seed counts only if EVERY size has a record for EVERY tabulated solver
    # -- otherwise the table would silently compare a 10-seed row against a
    # 4-seed one. Judged per column, not by a raw count: the run also carries
    # highs-hull, which the table does not show.
    have = collections.defaultdict(set)
    for r in rows:
        have[(int(r["size"]), int(r["seed"]))].add(r["solver"])
    sizes = sorted({int(r["size"]) for r in rows})
    want = {s for s, _ in COLS}
    seeds = sorted({int(r["seed"]) for r in rows})
    complete = [s for s in seeds
                if all(want <= have.get((n, s), set()) for n in sizes)]
    K = args.seeds if args.seeds is not None else len(complete)
    use = complete[:K]
    if len(use) < K:
        raise SystemExit(f"only {len(use)} complete seeds available, asked {K}")

    rows = [r for r in rows if int(r["seed"]) in use]
    by = collections.defaultdict(list)
    for r in rows:
        by[(int(r["size"]), r["solver"])].append(r)

    print(f"% seeds used: {use}  (K={K})   run={args.run}")
    body, spread = [], []
    for n in sizes:
        cells, raw = [], []
        for s, _ in COLS:
            rs = by.get((n, s), [])
            if not rs:
                cells.append(("--", INF))
                continue
            vals = [float(x["runtime_s"]) if x.get("proved_optimal") else INF
                    for x in rs]
            ok = [v for v in vals if v != INF]
            m = median(vals)
            txt = "T/O" if m == INF else f"{m:.2f}"
            if len(ok) < len(rs):                       # not every seed proved
                txt += f"$^{{{len(ok)}/{len(rs)}}}$"
            cells.append((txt, m))
            raw.append((s, min(ok) if ok else None, max(ok) if ok else None,
                        len(ok), len(rs)))
        best = min(m for _, m in cells)
        out = [(r"\textbf{" + t + "}") if m == best and m != INF else t
               for t, m in cells]
        body.append(f"{n:<3}& " + " & ".join(f"{c:<14}" for c in out) + r" \\")
        spread.append((n, raw))

    print("\n".join(body))

    if args.spread:
        print("\n% --- min-max per cell (for the prose) ---")
        for n, raw in spread:
            print(f"% n={n}")
            for s, lo, hi, ok, tot in raw:
                r = f"{lo:.2f}-{hi:.2f}" if lo is not None else "--"
                print(f"%   {s:<14}{r:>18}   proved {ok}/{tot}")


if __name__ == "__main__":
    main()
