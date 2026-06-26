"""CP encoding: structured spec -> OR-Tools CP-SAT model (native, in-process).

Unlike the MiniZinc text encoding (which targets Gecode/Chuffed), this builds a
CP-SAT model directly. Job-shop no-overlap uses native interval variables +
``AddNoOverlap`` -- the idiomatic, strong disjunctive-scheduling formulation --
rather than a hand-rolled big-M, so CP-SAT competes on its own terms. ortools is
imported lazily; ``bvcover`` is OMT-only and not encoded here.

``build_cpsat(spec)`` returns ``(model, objective_var, sense)``; the solver
adapter owns the solve loop (and the solution callback for anytime curves).
"""

from __future__ import annotations

from ..benchmarks.families import jobshop_ops


def gap_cpsat(s):
    from ortools.sat.python import cp_model
    n, m, c, w, C = s["n"], s["m"], s["c"], s["w"], s["C"]
    md = cp_model.CpModel()
    x = {(i, j): md.NewBoolVar(f"x_{i}_{j}") for i in range(n) for j in range(m)}
    for i in range(n):
        md.Add(sum(x[(i, j)] for j in range(m)) == 1)
    for j in range(m):
        md.Add(sum(w[i][j] * x[(i, j)] for i in range(n)) <= C[j])
    obj = md.NewIntVar(0, sum(max(row) for row in c), "__obj")
    md.Add(obj == sum(c[i][j] * x[(i, j)] for i in range(n) for j in range(m)))
    md.Minimize(obj)
    return md, obj, "min"


def knapsack_cpsat(s):
    from ortools.sat.python import cp_model
    n, R, v, w, C = s["n"], s["R"], s["v"], s["w"], s["C"]
    md = cp_model.CpModel()
    x = {i: md.NewBoolVar(f"x_{i}") for i in range(n)}
    for r in range(R):
        md.Add(sum(w[r][i] * x[i] for i in range(n)) <= C[r])
    obj = md.NewIntVar(0, sum(v), "__obj")
    md.Add(obj == sum(v[i] * x[i] for i in range(n)))
    md.Maximize(obj)
    return md, obj, "max"


def jobshop_cpsat(s):
    from ortools.sat.python import cp_model
    ops, H = jobshop_ops(s), s["H"]
    md = cp_model.CpModel()
    start, end, ivl = {}, {}, {}
    for o in ops:
        st = md.NewIntVar(0, H, f"st_{o['id']}")
        en = md.NewIntVar(0, H, f"en_{o['id']}")
        iv = md.NewIntervalVar(st, o["dur"], en, f"iv_{o['id']}")
        start[o["id"]], end[o["id"]], ivl[o["id"]] = st, en, iv
    # intra-job precedence
    byjob = {}
    for o in ops:
        byjob.setdefault(o["job"], []).append(o)
    for lst in byjob.values():
        lst.sort(key=lambda o: o["pos"])
        for a, b in zip(lst, lst[1:]):
            md.Add(start[b["id"]] >= end[a["id"]])
    # per-machine no-overlap (native disjunctive)
    bym = {}
    for o in ops:
        bym.setdefault(o["machine"], []).append(o)
    for lst in bym.values():
        md.AddNoOverlap([ivl[o["id"]] for o in lst])
    mk = md.NewIntVar(0, H, "__obj")
    md.AddMaxEquality(mk, [end[o["id"]] for o in ops])
    md.Minimize(mk)
    return md, mk, "min"


def config_cpsat(s):
    from ortools.sat.python import cp_model
    n, cost, perf, deps, mutex, T = (s["n"], s["cost"], s["perf"],
                                     s["deps"], s["mutex"], s["T"])
    md = cp_model.CpModel()
    sel = {i: md.NewBoolVar(f"sel_{i}") for i in range(n)}
    md.Add(sum(perf[i] * sel[i] for i in range(n)) >= T)
    for (i, j) in deps:
        md.AddImplication(sel[i], sel[j])
    for (i, j) in mutex:
        md.Add(sel[i] + sel[j] <= 1)
    obj = md.NewIntVar(0, sum(cost), "__obj")
    md.Add(obj == sum(cost[i] * sel[i] for i in range(n)))
    md.Minimize(obj)
    return md, obj, "min"


def setcover_cpsat(s):
    from ortools.sat.python import cp_model
    u, m, sets, cost = s["u"], s["m"], s["sets"], s["cost"]
    md = cp_model.CpModel()
    y = {j: md.NewBoolVar(f"y_{j}") for j in range(m)}
    for e in range(u):
        md.Add(sum(y[j] for j in range(m) if e in sets[j]) >= 1)
    obj = md.NewIntVar(0, sum(cost), "__obj")
    md.Add(obj == sum(cost[j] * y[j] for j in range(m)))
    md.Minimize(obj)
    return md, obj, "min"


_CPSAT = {
    "gap": gap_cpsat, "knapsack": knapsack_cpsat, "jobshop": jobshop_cpsat,
    "config": config_cpsat, "setcover": setcover_cpsat,
}

CPSAT_FAMILIES = frozenset(_CPSAT)


def build_cpsat(spec: dict):
    """Return (model, objective_var, sense), or None if not applicable."""
    fn = _CPSAT.get(spec["family"])
    return fn(spec) if fn else None
