#!/usr/bin/env python3
"""Generate the two aggregate manuscript tables from audited results."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = dict(z3="Z3", ocac="OCAC", optimathsat="OptiMathSAT", scipy="SLSQP",
              ipopt="IPOPT", gurobi="Gurobi", couenne="Couenne")


def table(caption, label, headers, rows):
    lines = [r"\begin{table}[H]", r"\centering", r"\caption{" + caption + "}",
             r"\label{" + label + "}", r"\small", r"\setlength{\tabcolsep}{6pt}",
             r"\begin{tabular}{@{}l" + "r"*(len(headers)-1) + "@{}}", r"\toprule",
             " & ".join(headers) + r" \\", r"\midrule"]
    for i, (solver, values) in enumerate(rows):
        if i == 3:
            lines.append(r"\midrule")
        lines.append(LABELS[solver] + " & " + " & ".join(map(str, values)) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def main():
    folder = ROOT / "runs/nra_public_20261102"
    audit = json.loads((folder / "delivery-audit.json").read_text())
    assert audit["passed"]
    data = audit["table"]
    solvers = ["z3", "ocac", "optimathsat", "scipy", "ipopt", "gurobi", "couenne"]
    rows = [(s, [data[s][str(n)] for n in (2, 3, 4, 5)] + [sum(data[s].values())]) for s in solvers]
    text = table("公开多变量非凸实例中达到参考最优值的数量", "tab:exp-nra-public",
                 ["求解器", "2 变量 (14)", "3 变量 (10)", "4 变量 (10)", "5 变量 (9)", "合计 (43)"], rows)
    (folder / "table.tex").write_text(text)
    folder = ROOT / "runs/nra_disjunctive_20261102"
    assert json.loads((folder / "delivery-audit.json").read_text())["passed"]
    data = json.loads((folder / "summary.json").read_text())
    rows = [(s, [data[s][str(n)]["hits"] for n in (4, 8, 12)] +
             [sum(data[s][str(n)]["hits"] for n in (4, 8, 12))])
            for s in ("z3", "ocac", "optimathsat", "gurobi", "couenne")]
    text = table("析取非线性实例中达到参考最优值的数量", "tab:exp-nra-disjunctive",
                 ["求解器", "4 单元 (3)", "8 单元 (3)", "12 单元 (3)", "合计 (9)"], rows)
    (folder / "table.tex").write_text(text)


if __name__ == "__main__":
    main()
