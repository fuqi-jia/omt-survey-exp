#!/usr/bin/env python3
"""Turn results.csv into LaTeX tables, figures, and a text summary.

Produces, under runs/<config>/:
  tables/time_by_family.tex        median solve time per (family, size, solver)
  tables/solved_by_category.tex    proven-optimal count per category x solver
  figures/runtime_<family>.png     median runtime vs size (log y), per family
  figures/anytime_<inst>.png       incumbent trajectory on a hard instance
  summary.md                       human-readable digest

Usage:
  python scripts/analyze.py --config configs/wsl.yaml
"""

import _bootstrap  # noqa: F401
import argparse
import json
import os

import yaml
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# canonical column order + display labels
SOLVER_ORDER = ["z3", "optimathsat", "cbc", "highs", "scip", "gurobi", "cplex",
                "gecode", "chuffed", "cpsat"]
SOLVER_LABEL = {
    "z3": r"$\nu$Z", "optimathsat": "OptiMathSAT", "cbc": "CBC",
    "highs": "HiGHS", "scip": "SCIP", "gurobi": "Gurobi", "cplex": "CPLEX",
    "gecode": "Gecode", "chuffed": "Chuffed", "cpsat": "CP-SAT",
}
PARADIGM = {"z3": "OMT", "optimathsat": "OMT", "cbc": "MILP", "highs": "MILP",
            "scip": "MILP", "gurobi": "MILP", "cplex": "MILP",
            "gecode": "CP", "chuffed": "CP", "cpsat": "CP"}
FAMILY_LABEL = {
    "gap": "Generalized assignment (A, linear)",
    "knapsack": "Multidim. knapsack (A, linear)",
    "jobshop": "Job-shop scheduling (B, disjunctive)",
    "config": "System configuration (B, deps+mutex)",
    "setcover": "Weighted set cover (B, covering)",
    "bvcover": "Bit-vector cover (C, BV; OMT-only)",
}


def present_solvers(df):
    return [s for s in SOLVER_ORDER if s in set(df["solver"])]


def agg(df):
    """Per (family, category, size, solver): n_total, n_proved, median time."""
    g = df.groupby(["family", "category", "size", "solver"])
    rows = []
    for (fam, cat, size, solver), sub in g:
        proved = sub[sub["proved_optimal"]]
        rows.append({
            "family": fam, "category": cat, "size": int(size), "solver": solver,
            "n_total": len(sub), "n_proved": len(proved),
            "med_time": proved["runtime_s"].median() if len(proved) else None,
        })
    return pd.DataFrame(rows)


def _cell(r):
    if r is None or r["n_proved"] == 0:
        return "T/O"
    s = f"{r['med_time']:.3f}"
    if r["n_proved"] < r["n_total"]:
        s += f"$^{{{r['n_proved']}/{r['n_total']}}}$"
    return s


def table_time(a, solvers, out):
    cols = "l" + "r" * len(solvers)
    L = [r"\begin{table}[t]", r"\centering",
         r"\caption{Median solve time (s, single-thread). "
         r"T/O = all seeds timed out; superscript $n/m$ = $n$ of $m$ seeds proved optimal.}",
         r"\label{tab:exp-time}", r"\small", r"\setlength{\tabcolsep}{5pt}",
         r"\begin{tabular}{@{}" + cols + r"@{}}", r"\toprule",
         "Size & " + " & ".join(SOLVER_LABEL[s] for s in solvers) + r" \\",
         r"\midrule"]
    for fam in [f for f in FAMILY_LABEL if f in set(a["family"])]:
        sub = a[a["family"] == fam]
        L.append(r"\multicolumn{%d}{@{}l}{%s} \\" % (len(solvers) + 1, FAMILY_LABEL[fam]))
        for size in sorted(sub["size"].unique()):
            cells = []
            for s in solvers:
                row = sub[(sub["size"] == size) & (sub["solver"] == s)]
                cells.append(_cell(row.iloc[0]) if len(row) else "--")
            L.append(f"{size} & " + " & ".join(cells) + r" \\")
        L.append(r"\midrule")
    if L[-1] == r"\midrule":
        L[-1] = r"\bottomrule"
    else:
        L.append(r"\bottomrule")
    L += [r"\end{tabular}", r"\end{table}"]
    with open(os.path.join(out, "tables", "time_by_family.tex"), "w") as f:
        f.write("\n".join(L) + "\n")


def table_solved(df, solvers, out):
    cats = sorted(df["category"].unique())
    cols = "l" + "r" * len(solvers)
    L = [r"\begin{table}[t]", r"\centering",
         r"\caption{Instances proved optimal (solved/total) per category.}",
         r"\label{tab:exp-solved}", r"\small",
         r"\begin{tabular}{@{}" + cols + r"@{}}", r"\toprule",
         "Category & " + " & ".join(SOLVER_LABEL[s] for s in solvers) + r" \\",
         r"\midrule"]
    for cat in cats:
        cells = []
        for s in solvers:
            sub = df[(df["category"] == cat) & (df["solver"] == s)]
            if len(sub) == 0:
                cells.append("--")
            else:
                cells.append(f"{int(sub['proved_optimal'].sum())}/{len(sub)}")
        L.append(f"{cat} & " + " & ".join(cells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    with open(os.path.join(out, "tables", "solved_by_category.tex"), "w") as f:
        f.write("\n".join(L) + "\n")


def fig_runtime(a, solvers, out, timeout):
    for fam in [f for f in FAMILY_LABEL if f in set(a["family"])]:
        sub = a[a["family"] == fam]
        plt.figure(figsize=(5, 3.2))
        for s in solvers:
            ss = sub[sub["solver"] == s].sort_values("size")
            xs, ys = [], []
            for _, r in ss.iterrows():
                xs.append(r["size"])
                ys.append(r["med_time"] if r["n_proved"] else timeout)
            if xs:
                plt.plot(xs, ys, marker="o", label=SOLVER_LABEL[s])
        plt.yscale("log")
        plt.xlabel("size $n$")
        plt.ylabel("median time (s)")
        plt.title(FAMILY_LABEL[fam])
        plt.grid(True, which="both", ls=":", alpha=0.5)
        plt.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(os.path.join(out, "figures", f"runtime_{fam}.png"), dpi=130)
        plt.close()


def fig_anytime(rows, out):
    """Plot incumbent trajectories for the instance with the richest curves."""
    best_inst, best_score = None, -1
    by_inst = {}
    for r in rows:
        incs = r.get("incumbents") or []
        by_inst.setdefault(r["name"], []).append((r["solver"], incs, r.get("sense", "min")))
    for name, lst in by_inst.items():
        score = sum(len(incs) for _, incs, _ in lst if len(incs) >= 2)
        if score > best_score:
            best_score, best_inst = score, name
    if not best_inst or best_score < 2:
        return None
    plt.figure(figsize=(5, 3.2))
    plotted = 0
    for solver, incs, _ in by_inst[best_inst]:
        if len(incs) >= 2:
            xs = [t for t, _ in incs]
            ys = [o for _, o in incs]
            plt.step(xs, ys, where="post", marker=".",
                     label=SOLVER_LABEL.get(solver, solver))
            plotted += 1
    if not plotted:
        plt.close()
        return None
    plt.xlabel("time (s)")
    plt.ylabel("incumbent objective")
    plt.title(f"Anytime incumbents: {best_inst}")
    plt.grid(True, ls=":", alpha=0.5)
    plt.legend(fontsize=7)
    plt.tight_layout()
    path = os.path.join(out, "figures", f"anytime_{best_inst}.png")
    plt.savefig(path, dpi=130)
    plt.close()
    return best_inst


def write_summary(df, a, solvers, out, anytime_inst):
    L = [f"# Experiment summary: {os.path.basename(out)}", "",
         f"- Total runs: {len(df)}",
         f"- Solvers: {', '.join(SOLVER_LABEL[s]+' ('+PARADIGM[s]+')' for s in solvers)}",
         f"- Instances: {df['name'].nunique()}", "",
         "## Proved optimal per category", ""]
    cats = sorted(df["category"].unique())
    L.append("| Category | " + " | ".join(SOLVER_LABEL[s] for s in solvers) + " |")
    L.append("|" + "---|" * (len(solvers) + 1))
    for cat in cats:
        cells = []
        for s in solvers:
            sub = df[(df["category"] == cat) & (df["solver"] == s)]
            cells.append(f"{int(sub['proved_optimal'].sum())}/{len(sub)}" if len(sub) else "--")
        L.append(f"| {cat} | " + " | ".join(cells) + " |")
    L += ["", "## Notes", "",
          "- Median solve time and solved/total tables: see `tables/`.",
          "- Per-family scaling curves and anytime trajectory: see `figures/`."]
    if anytime_inst:
        L.append(f"- Anytime example instance: `{anytime_inst}`.")
    with open(os.path.join(out, "summary.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    out = os.path.join(REPO, "runs", cfg["name"])
    timeout = float(cfg.get("timeout", 60))
    for d in ("tables", "figures"):
        os.makedirs(os.path.join(out, d), exist_ok=True)

    df = pd.read_csv(os.path.join(out, "results.csv"))
    df["proved_optimal"] = df["proved_optimal"].astype(bool)
    rows = json.load(open(os.path.join(out, "results.json")))

    solvers = present_solvers(df)
    a = agg(df)
    table_time(a, solvers, out)
    table_solved(df, solvers, out)
    fig_runtime(a, solvers, out, timeout)
    anytime_inst = fig_anytime(rows, out)
    write_summary(df, a, solvers, out, anytime_inst)
    print(f"\nWrote tables/ and figures/ to {os.path.relpath(out, REPO)}/")


if __name__ == "__main__":
    main()
