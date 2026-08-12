#!/usr/bin/env python3
"""Merge the Windows full-licence Gurobi run into a config's main results.

Both source files stay PRISTINE; this only rebuilds the derived
``results.csv`` / ``results.json`` that ``analyze.py`` consumes:

    runs/<cfg>/results.jsonl             WSL harness, all solvers   (untouched)
    runs/<cfg>/gurobi_win/results.jsonl  Windows full Gurobi        (untouched)
    runs/<cfg>/results.csv/.json         <- rebuilt by this script

Merge policy
------------
Take the WSL row for every (instance, gurobi-ind) pair it actually solved, and
substitute the Windows row ONLY where WSL failed *because of the size-limited
licence*. Rationale: on the cells both environments solved, objectives are
identical and the runtime ratio is ~1, so the two are interchangeable there --
and keeping the column on one platform avoids importing cross-platform search
nondeterminism into an otherwise-Linux table. The licence cap, not the platform,
is the only reason to reach for the Windows data at all.

Substituted rows are tagged ``"source": "gurobi_win"`` so provenance survives
into results.json. Every other row is tagged ``"source": "wsl"``.

Cells where the two environments DISAGREE on status (other than the licence
errors being fixed) are reported loudly -- they are data-quality notes for
DATA_PROVENANCE.md, not something to silently paper over.

Usage:
    python scripts/merge_gurobi_win.py --config configs/long600.yaml
"""

import argparse
import csv
import json
import os
import sys

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CSV_FIELDS = [
    "name", "family", "category", "size", "seed", "paradigm", "solver",
    "status", "proved_optimal", "objective", "runtime_s", "memory_peak_mb",
    "best_at_10s", "best_at_30s", "best_at_60s", "timeout_s",
]

LICENCE_MARK = "size-limited"


def read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    out = os.path.join(REPO, "runs", cfg["name"])
    main_rows = read_jsonl(os.path.join(out, "results.jsonl"))
    win_rows = read_jsonl(os.path.join(out, "gurobi_win", "results.jsonl"))
    if not win_rows:
        sys.exit(f"no Windows Gurobi results under {out}/gurobi_win/")
    win = {r["name"]: r for r in win_rows}

    replaced, disagree, kept = [], [], 0
    merged = []
    for r in main_rows:
        r = dict(r)
        if r.get("solver") != "gurobi-ind":
            r["source"] = "wsl"
            merged.append(r)
            continue
        w = win.get(r["name"])
        capped = (r.get("status") == "ERROR"
                  and LICENCE_MARK in (r.get("error_message") or ""))
        if capped and w is not None:
            w = dict(w)
            w["source"] = "gurobi_win"
            merged.append(w)
            replaced.append((r["name"], w.get("status"), w.get("runtime_s")))
            continue
        if w is not None and w.get("status") != r.get("status"):
            disagree.append((r["name"], r.get("status"), r.get("runtime_s"),
                             w.get("status"), w.get("runtime_s")))
        r["source"] = "wsl"
        merged.append(r)
        kept += 1

    print(f"gurobi-ind rows kept from WSL   : {kept}")
    print(f"gurobi-ind rows from Windows    : {len(replaced)}  (licence-capped cells)")
    for nm, stt, rt in replaced:
        print(f"    + {nm:<22} {stt:<8} {rt:.3f}s")
    if disagree:
        print(f"\n!! status disagreements on cells BOTH environments attempted "
              f"({len(disagree)}) -- record in DATA_PROVENANCE.md, not merged:")
        for nm, s1, t1, s2, t2 in disagree:
            print(f"    {nm:<22} wsl={s1}({t1}s)  win={s2}({t2}s)")

    # ---- correctness cross-check on the MERGED set ----
    by_inst = {}
    for r in merged:
        if r.get("proved_optimal") and r.get("objective") is not None:
            by_inst.setdefault(r["name"], []).append((r["solver"], r["objective"]))
    mism = n_cross = 0
    for name, lst in sorted(by_inst.items()):
        if len(lst) > 1:
            n_cross += 1
            if len({v for _, v in lst}) > 1:
                mism += 1
                print(f"  MISMATCH {name}: {lst}")
    print(f"\n=== cross-check on merged set ===")
    print(f"  {'OK: ' if not mism else ''}{n_cross} multi-solver instances, "
          f"{mism} mismatch(es)")

    with open(os.path.join(out, "results.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        wr.writeheader()
        for r in merged:
            wr.writerow(r)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(merged, f, indent=1, ensure_ascii=False, default=str)
    print(f"\nRebuilt results.csv / results.json ({len(merged)} rows) in "
          f"{os.path.relpath(out, REPO)}/")


if __name__ == "__main__":
    main()
