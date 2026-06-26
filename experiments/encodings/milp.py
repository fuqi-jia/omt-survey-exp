"""MILP encoding: structured spec -> PuLP model.

Disjunctions (job-shop no-overlap) are linearized with the classic big-M trick,
which is exactly the encoding cost the survey contrasts against OMT's native
boolean handling. ``pulp`` is imported lazily so this module is importable on a
machine without it; ``bvcover`` has no MILP encoding (bit-level reasoning needs
bit-blasting, which is the whole point of the OMT-only family).
"""

from __future__ import annotations

from ..benchmarks.families import jobshop_ops


def gap_pulp(s):
    import pulp
    n, m, c, w, C = s["n"], s["m"], s["c"], s["w"], s["C"]
    p = pulp.LpProblem("gap", pulp.LpMinimize)
    x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary")
         for i in range(n) for j in range(m)}
    p += pulp.lpSum(c[i][j] * x[(i, j)] for i in range(n) for j in range(m))
    for i in range(n):
        p += pulp.lpSum(x[(i, j)] for j in range(m)) == 1
    for j in range(m):
        p += pulp.lpSum(w[i][j] * x[(i, j)] for i in range(n)) <= C[j]
    return p


def knapsack_pulp(s):
    import pulp
    n, R, v, w, C = s["n"], s["R"], s["v"], s["w"], s["C"]
    p = pulp.LpProblem("knap", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n)}
    p += pulp.lpSum(v[i] * x[i] for i in range(n))
    for r in range(R):
        p += pulp.lpSum(w[r][i] * x[i] for i in range(n)) <= C[r]
    return p


def jobshop_pulp(s):
    import pulp
    ops, H = jobshop_ops(s), s["H"]
    p = pulp.LpProblem("jobshop", pulp.LpMinimize)
    st = {o["id"]: pulp.LpVariable(f"st_{o['id']}", 0, H, cat="Integer") for o in ops}
    mk = pulp.LpVariable("makespan", 0, H, cat="Integer")
    p += mk
    byjob = {}
    for o in ops:
        byjob.setdefault(o["job"], []).append(o)
    for lst in byjob.values():
        lst.sort(key=lambda o: o["pos"])
        for a, b in zip(lst, lst[1:]):
            p += st[b["id"]] >= st[a["id"]] + a["dur"]
    bym = {}
    for o in ops:
        bym.setdefault(o["machine"], []).append(o)
    pair = 0
    for lst in bym.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                y = pulp.LpVariable(f"y_{pair}", cat="Binary"); pair += 1
                # big-M disjunction: y=1 -> a before b ; y=0 -> b before a
                p += st[a["id"]] + a["dur"] <= st[b["id"]] + H * (1 - y)
                p += st[b["id"]] + b["dur"] <= st[a["id"]] + H * y
    for o in ops:
        p += mk >= st[o["id"]] + o["dur"]
    return p


def config_pulp(s):
    import pulp
    n, cost, perf, deps, mutex, T = (s["n"], s["cost"], s["perf"],
                                     s["deps"], s["mutex"], s["T"])
    p = pulp.LpProblem("config", pulp.LpMinimize)
    sel = {i: pulp.LpVariable(f"sel_{i}", cat="Binary") for i in range(n)}
    p += pulp.lpSum(cost[i] * sel[i] for i in range(n))
    p += pulp.lpSum(perf[i] * sel[i] for i in range(n)) >= T
    for (i, j) in deps:
        p += sel[i] <= sel[j]            # sel_i => sel_j
    for (i, j) in mutex:
        p += sel[i] + sel[j] <= 1
    return p


def setcover_pulp(s):
    import pulp
    u, m, sets, cost = s["u"], s["m"], s["sets"], s["cost"]
    p = pulp.LpProblem("setcover", pulp.LpMinimize)
    y = {j: pulp.LpVariable(f"y_{j}", cat="Binary") for j in range(m)}
    p += pulp.lpSum(cost[j] * y[j] for j in range(m))
    for e in range(u):
        p += pulp.lpSum(y[j] for j in range(m) if e in sets[j]) >= 1
    return p


_PULP = {
    "gap": gap_pulp, "knapsack": knapsack_pulp, "jobshop": jobshop_pulp,
    "config": config_pulp, "setcover": setcover_pulp,
}

# families that have a MILP encoding
MILP_FAMILIES = frozenset(_PULP)


def to_pulp(spec: dict):
    """Build a fresh PuLP model for the instance (or None if not applicable)."""
    fn = _PULP.get(spec["family"])
    return fn(spec) if fn else None
