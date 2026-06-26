"""CP encoding: structured spec -> MiniZinc model text (for Gecode / Chuffed).

Disjunctions are written natively with ``\\/`` (no big-M), so the FlatZinc that
Gecode/Chuffed receive keeps the disjunctive structure -- the comparison point
against the MILP big-M encoding. ``bvcover`` has no CP encoding here (bit-level
``bvand`` has no natural finite-domain model and is reserved for OMT).
"""

from __future__ import annotations

from ..benchmarks.families import jobshop_ops


def gap_mzn(s):
    n, m, c, w, C = s["n"], s["m"], s["c"], s["w"], s["C"]
    L = [f"int: n = {n};", f"int: m = {m};",
         "array[1..n,1..m] of int: c = array2d(1..n,1..m, " +
         str([c[i][j] for i in range(n) for j in range(m)]) + ");",
         "array[1..n,1..m] of int: w = array2d(1..n,1..m, " +
         str([w[i][j] for i in range(n) for j in range(m)]) + ");",
         "array[1..m] of int: C = " + str(C) + ";",
         "array[1..n,1..m] of var 0..1: x;",
         "constraint forall(i in 1..n)(sum(j in 1..m)(x[i,j]) = 1);",
         "constraint forall(j in 1..m)(sum(i in 1..n)(w[i,j]*x[i,j]) <= C[j]);",
         "solve minimize sum(i in 1..n, j in 1..m)(c[i,j]*x[i,j]);"]
    return "\n".join(L) + "\n"


def knapsack_mzn(s):
    n, R, v, w, C = s["n"], s["R"], s["v"], s["w"], s["C"]
    L = [f"int: n = {n};", f"int: R = {R};", "array[1..n] of int: v = " + str(v) + ";",
         "array[1..R,1..n] of int: w = array2d(1..R,1..n, " +
         str([w[r][i] for r in range(R) for i in range(n)]) + ");",
         "array[1..R] of int: C = " + str(C) + ";",
         "array[1..n] of var 0..1: x;",
         "constraint forall(r in 1..R)(sum(i in 1..n)(w[r,i]*x[i]) <= C[r]);",
         "solve maximize sum(i in 1..n)(v[i]*x[i]);"]
    return "\n".join(L) + "\n"


def jobshop_mzn(s):
    ops, H = jobshop_ops(s), s["H"]
    nops = len(ops)
    dur = [o["dur"] for o in ops]
    L = [f"int: nops = {nops};", f"int: H = {H};",
         f"array[1..nops] of int: dur = {dur};",
         "array[1..nops] of var 0..H: st;",
         "var 0..H: makespan;"]
    byjob = {}
    for o in ops:
        byjob.setdefault(o["job"], []).append(o)
    for lst in byjob.values():
        lst.sort(key=lambda o: o["pos"])
        for a, b in zip(lst, lst[1:]):
            L.append(f"constraint st[{b['id']+1}] >= st[{a['id']+1}] + {a['dur']};")
    bym = {}
    for o in ops:
        bym.setdefault(o["machine"], []).append(o)
    for lst in bym.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                L.append(f"constraint (st[{a['id']+1}] + {a['dur']} <= st[{b['id']+1}]) "
                         f"\\/ (st[{b['id']+1}] + {b['dur']} <= st[{a['id']+1}]);")
    L.append("constraint forall(o in 1..nops)(makespan >= st[o] + dur[o]);")
    L.append("solve minimize makespan;")
    return "\n".join(L) + "\n"


def config_mzn(s):
    n, cost, perf, deps, mutex, T = (s["n"], s["cost"], s["perf"],
                                     s["deps"], s["mutex"], s["T"])
    L = [f"int: n = {n};", f"array[1..n] of int: cost = {cost};",
         f"array[1..n] of int: perf = {perf};", f"int: T = {T};",
         "array[1..n] of var 0..1: sel;",
         "constraint sum(i in 1..n)(perf[i]*sel[i]) >= T;"]
    for (i, j) in deps:
        L.append(f"constraint sel[{i+1}] <= sel[{j+1}];")
    for (i, j) in mutex:
        L.append(f"constraint sel[{i+1}] + sel[{j+1}] <= 1;")
    L.append("solve minimize sum(i in 1..n)(cost[i]*sel[i]);")
    return "\n".join(L) + "\n"


def setcover_mzn(s):
    u, m, sets, cost = s["u"], s["m"], s["sets"], s["cost"]
    L = [f"int: m = {m};", "array[1..m] of int: cost = " + str(cost) + ";",
         "array[1..m] of var 0..1: y;"]
    for e in range(u):
        cov = [j + 1 for j in range(m) if e in sets[j]]
        L.append("constraint " + " + ".join(f"y[{j}]" for j in cov) + " >= 1;")
    L.append("solve minimize sum(j in 1..m)(cost[j]*y[j]);")
    return "\n".join(L) + "\n"


_MZN = {
    "gap": gap_mzn, "knapsack": knapsack_mzn, "jobshop": jobshop_mzn,
    "config": config_mzn, "setcover": setcover_mzn,
}

CP_FAMILIES = frozenset(_MZN)


def to_minizinc(spec: dict):
    fn = _MZN.get(spec["family"])
    return fn(spec) if fn else None
