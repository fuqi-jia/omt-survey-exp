#!/usr/bin/env python3
"""Plot observed cumulative job-shop call times from the archived cohort."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator


ROOT = Path(__file__).resolve().parents[1]
SIZES = (7, 8, 9, 10)
GROUPS = (
    ("OMT", (
        ("z3", "νZ", "#32658A", "-", "o"),
        ("optimathsat", "OptiMathSAT", "#B37D3C", "--", "s"),
    )),
    ("开源 MILP", (
        ("cbc-bigm", "CBC", "#68727E", "-", "o"),
        ("highs-bigm", "HiGHS", "#39847F", "--", "s"),
        ("scip-bigm", "SCIP", "#8B709B", "-.", "^"),
    )),
    ("商用 MILP", (
        ("gurobi-bigm", "Gurobi (大M)", "#367B67", "-", "o"),
        ("gurobi-ind", "Gurobi (指示)", "#367B67", "--", "s"),
        ("cplex-bigm", "CPLEX (大M)", "#A46664", "-", "^"),
        ("cplex-ind", "CPLEX (指示)", "#A46664", "--", "D"),
    )),
    ("CP", (
        ("gecode", "Gecode", "#907044", "-", "o"),
        ("cpsat", "CP-SAT", "#39847F", "--", "s"),
    )),
)


def configure_fonts(font_dir: Path | None):
    candidates = ([font_dir] if font_dir else []) + [
        Path("/mnt/c/Windows/Fonts"), Path("C:/Windows/Fonts"),
    ]
    directory = next((p for p in candidates if p and (p / "simsun.ttc").is_file()), None)
    if directory is None:
        raise FileNotFoundError("Supply --font-dir containing simsun.ttc, simhei.ttf and arial.ttf")
    files = {"body": directory / "simsun.ttc", "title": directory / "simhei.ttf",
             "latin": directory / "arial.ttf"}
    for path in files.values():
        font_manager.fontManager.addfont(str(path))
    mpl.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial"],
        "font.size": 7.2, "axes.titlesize": 8.2, "axes.labelsize": 8,
        "xtick.labelsize": 7.2, "ytick.labelsize": 7.2,
        "legend.fontsize": 7, "legend.frameon": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "axes.edgecolor": "#41464B",
        "axes.unicode_minus": False, "pdf.fonttype": 42, "svg.fonttype": "none",
        "savefig.dpi": 600,
    })

    def font(kind="body", size=8):
        return font_manager.FontProperties(fname=str(files[kind]), size=size)

    return font


def load_calls(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    solvers = {entry[0] for _, group in GROUPS for entry in group}
    cohort = [row for row in all_rows if row["family"] == "jobshop"]
    selected = [row for row in cohort if row["solver"] in solvers]
    assert len(cohort) == 480 and len(selected) == 440
    keys = {(row["solver"], int(row["size"]), int(row["seed"])) for row in selected}
    assert len(keys) == len(selected)
    summary = {}
    for solver in sorted(solvers):
        summary[solver] = []
        for size in SIZES:
            rows = sorted((row for row in selected if row["solver"] == solver
                           and int(row["size"]) == size), key=lambda row: int(row["seed"]))
            assert [int(row["seed"]) for row in rows] == list(range(10))
            times = [float(row["runtime_s"]) for row in rows]
            assert all(math.isfinite(value) and value > 0 for value in times)
            summary[solver].append({
                "size": size, "calls": 10,
                "proved_optimal": sum(row["proved_optimal"] == "True" for row in rows),
                "total_runtime_s": math.fsum(times),
            })
    return selected, summary


def draw(summary, output: Path, font, qa_scripts: Path):
    sys.path.insert(0, str(qa_scripts))
    from audit_panel_alignment import require_matplotlib_panel_alignment

    fig, axes = plt.subplots(2, 2, sharex=True, sharey=True,
                             figsize=(155.15 / 25.4, 88 / 25.4))
    fig.subplots_adjust(left=0.105, right=0.99, bottom=0.12, top=0.925,
                        wspace=0.18, hspace=0.35)
    assert all(b > a for a, b in zip(SIZES, SIZES[1:]))
    for index, (ax, (title, series)) in enumerate(zip(axes.flat, GROUPS)):
        ax.set_yscale("log")
        ax.set_ylim(0.08, 10000)
        ax.set_xlim(6.85, 10.15)
        ax.set_xticks(SIZES)
        ax.yaxis.set_major_locator(FixedLocator([0.1, 1, 10, 100, 1000, 10000]))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.yaxis.set_minor_locator(NullLocator())
        ax.grid(False)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", length=2.5, width=0.6, pad=2)
        ax.annotate(chr(ord("a") + index), xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 6), textcoords="offset points", fontweight="bold",
                    fontsize=8.2, ha="left", va="bottom")
        ax.annotate(title, xy=(0, 1), xycoords="axes fraction", xytext=(13, 6),
                    textcoords="offset points", fontproperties=font("title", 8.2),
                    ha="left", va="bottom")
        for solver, label, color, style, marker in series:
            points = summary[solver]
            y = [point["total_runtime_s"] for point in points]
            complete = [i for i, point in enumerate(points) if point["proved_optimal"] == 10]
            unfinished = [i for i, point in enumerate(points) if point["proved_optimal"] < 10]
            ax.plot(SIZES, y, label=label, color=color, linestyle=style, linewidth=1.2,
                    marker=marker, markevery=complete, markersize=3.2, markeredgewidth=0.6)
            if unfinished:
                ax.plot([SIZES[i] for i in unfinished], [y[i] for i in unfinished],
                        linestyle="none", marker="x", markersize=4.5,
                        markeredgewidth=1.1, color=color)
        ax.legend(loc="upper left" if index == 3 else "lower right",
                  prop=font("body", 7), handlelength=1.7, handletextpad=0.45,
                  borderaxespad=0.5, labelspacing=0.35, ncol=2 if index == 2 else 1,
                  columnspacing=0.8)
    fig.text(0.547, 0.02, "作业数 n", ha="center", va="bottom", fontproperties=font(size=8))
    fig.text(0.018, 0.53, "累计调用耗时 (秒)", ha="center", va="center", rotation=90,
             rotation_mode="anchor", fontproperties=font(size=8))
    fig.canvas.draw()
    require_matplotlib_panel_alignment(
        fig, json_out=output / "alignment.json", overlay_svg=output / "alignment.svg",
        tolerance_pt=1.5, gutter_tolerance_pt=1.5, require_panel_labels=True, strict=True,
    )
    fig.savefig(output / "jobshop-cumulative.pdf")
    fig.savefig(output / "jobshop-cumulative.svg")
    svg = output / "jobshop-cumulative.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    fig.savefig(output / "jobshop-cumulative.png", dpi=600)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path,
                        default=ROOT / "runs/paper_refresh_20261030/results.csv")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "runs/jobshop_figure_20261106")
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--qa-scripts", type=Path,
                        default=Path.home() / ".codex/skills/nature-figure/scripts")
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    calls, summary = load_calls(args.results)
    fields = ["name", "size", "seed", "solver", "status", "proved_optimal", "runtime_s"]
    with (output / "source-data.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(calls, key=lambda row: (row["solver"], int(row["size"]),
                                                       int(row["seed"]))))
    with (output / "plot-data.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["solver", "size", "calls",
                                                   "proved_optimal", "total_runtime_s"])
        writer.writeheader()
        for solver, points in summary.items():
            writer.writerows({"solver": solver, **point} for point in points)
    provenance = {
        "source": "runs/paper_refresh_20261030/results.csv",
        "source_sha256": hashlib.sha256(args.results.read_bytes()).hexdigest(),
        "jobshop_rows_before_selection": 480, "included_rows": len(calls),
        "selection": "All 11 configurations in the manuscript scheduling table; all four sizes and ten generation seeds.",
        "excluded_configuration": "highs-hull (40 calls); the separate convex-hull encoding is not a column in the scheduling table.",
        "metric": "Sum of recorded runtime_s for all ten calls at each problem size, including calls not proving optimality.",
        "uncertainty": "None: observed totals only, as requested by the author.",
        "unfinished_marker": "x at a size with fewer than ten proved-optimal calls",
        "figure_size_mm": [155.15, 88], "summary": summary,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    draw(summary, output, configure_fonts(args.font_dir), args.qa_scripts)
    print(f"Rendered 44 totals from {len(calls)} archived solver calls.")


if __name__ == "__main__":
    main()
