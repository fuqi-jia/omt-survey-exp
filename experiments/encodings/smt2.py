"""OMT encoding: structured spec -> SMT-LIB2 with an OMT objective.

Conventions that make the result solver-agnostic across nuZ (Z3) and
OptiMathSAT:

* ``(set-option :produce-models true)`` -- OptiMathSAT refuses to report an
  objective value without it (Z3 ignores the redundant option).
* a single objective variable ``__obj`` is always declared and bound, then
  ``(minimize __obj)`` / ``(maximize __obj)`` -- so the runner can parse the
  value uniformly from the ``(__obj <value>)`` line of ``(get-objectives)``.

OptiMathSAT additionally needs the command-line flag ``-optimization=TRUE``
(supplied by the solver adapter, not the file).
"""

from __future__ import annotations

from ..benchmarks.families import jobshop_ops


def _header(logic: str) -> list:
    return ["(set-option :produce-models true)", f"(set-logic {logic})"]


def gap_smt2(s):
    n, m, c, w, C = s["n"], s["m"], s["c"], s["w"], s["C"]
    L = _header("QF_LIA")
    for i in range(n):
        for j in range(m):
            L += [f"(declare-fun x_{i}_{j} () Int)",
                  f"(assert (>= x_{i}_{j} 0))", f"(assert (<= x_{i}_{j} 1))"]
    for i in range(n):
        L.append(f"(assert (= (+ {' '.join(f'x_{i}_{j}' for j in range(m))}) 1))")
    for j in range(m):
        terms = " ".join(f"(* {w[i][j]} x_{i}_{j})" for i in range(n))
        L.append(f"(assert (<= (+ {terms}) {C[j]}))")
    obj = " ".join(f"(* {c[i][j]} x_{i}_{j})" for i in range(n) for j in range(m))
    L += ["(declare-fun __obj () Int)", f"(assert (= __obj (+ {obj})))",
          "(minimize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


def knapsack_smt2(s):
    n, R, v, w, C = s["n"], s["R"], s["v"], s["w"], s["C"]
    L = _header("QF_LIA")
    for i in range(n):
        L += [f"(declare-fun x_{i} () Int)",
              f"(assert (>= x_{i} 0))", f"(assert (<= x_{i} 1))"]
    for r in range(R):
        terms = " ".join(f"(* {w[r][i]} x_{i})" for i in range(n))
        L.append(f"(assert (<= (+ {terms}) {C[r]}))")
    obj = " ".join(f"(* {v[i]} x_{i})" for i in range(n))
    L += ["(declare-fun __obj () Int)", f"(assert (= __obj (+ {obj})))",
          "(maximize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


def jobshop_smt2(s):
    ops, H = jobshop_ops(s), s["H"]
    L = _header("QF_LIA")
    for o in ops:
        L += [f"(declare-fun st_{o['id']} () Int)",
              f"(assert (>= st_{o['id']} 0))",
              f"(assert (<= (+ st_{o['id']} {o['dur']}) {H}))"]
    L.append("(declare-fun __obj () Int)")
    byjob = {}
    for o in ops:
        byjob.setdefault(o["job"], []).append(o)
    for lst in byjob.values():
        lst.sort(key=lambda o: o["pos"])
        for a, b in zip(lst, lst[1:]):
            L.append(f"(assert (>= st_{b['id']} (+ st_{a['id']} {a['dur']})))")
    bym = {}
    for o in ops:
        bym.setdefault(o["machine"], []).append(o)
    for lst in bym.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                L.append(f"(assert (or (<= (+ st_{a['id']} {a['dur']}) st_{b['id']}) "
                         f"(<= (+ st_{b['id']} {b['dur']}) st_{a['id']})))")
    for o in ops:
        L.append(f"(assert (>= __obj (+ st_{o['id']} {o['dur']})))")
    L += ["(minimize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


def config_smt2(s):
    n, cost, perf, deps, mutex, T = (s["n"], s["cost"], s["perf"],
                                     s["deps"], s["mutex"], s["T"])
    L = _header("QF_LIA")
    for i in range(n):
        L += [f"(declare-fun sel_{i} () Int)",
              f"(assert (>= sel_{i} 0))", f"(assert (<= sel_{i} 1))"]
    L.append(f"(assert (>= (+ {' '.join(f'(* {perf[i]} sel_{i})' for i in range(n))}) {T}))")
    for (i, j) in deps:
        L.append(f"(assert (=> (= sel_{i} 1) (= sel_{j} 1)))")
    for (i, j) in mutex:
        L.append(f"(assert (<= (+ sel_{i} sel_{j}) 1))")
    obj = " ".join(f"(* {cost[i]} sel_{i})" for i in range(n))
    L += ["(declare-fun __obj () Int)", f"(assert (= __obj (+ {obj})))",
          "(minimize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


def setcover_smt2(s):
    u, m, sets, cost = s["u"], s["m"], s["sets"], s["cost"]
    L = _header("QF_LIA")
    for j in range(m):
        L += [f"(declare-fun y_{j} () Int)",
              f"(assert (>= y_{j} 0))", f"(assert (<= y_{j} 1))"]
    for e in range(u):
        cov = [f"y_{j}" for j in range(m) if e in sets[j]]
        expr = f"(+ {' '.join(cov)})" if len(cov) > 1 else cov[0]
        L.append(f"(assert (>= {expr} 1))")
    obj = " ".join(f"(* {cost[j]} y_{j})" for j in range(m))
    L += ["(declare-fun __obj () Int)", f"(assert (= __obj (+ {obj})))",
          "(minimize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


def bvcover_smt2(s):
    w, forbidden, clauses = s["w"], s["forbidden"], s["clauses"]
    z = f"(_ bv0 {w})"
    L = _header("QF_BV")
    L.append(f"(declare-fun x () (_ BitVec {w}))")
    L.append(f"(assert (= (bvand x (_ bv{forbidden} {w})) {z}))")
    for cm in clauses:
        L.append(f"(assert (not (= (bvand x (_ bv{cm} {w})) {z})))")
    L += [f"(declare-fun __obj () (_ BitVec {w}))", "(assert (= __obj x))",
          "(minimize __obj)", "(check-sat)", "(get-objectives)"]
    return "\n".join(L) + "\n"


_SMT2 = {
    "gap": gap_smt2, "knapsack": knapsack_smt2, "jobshop": jobshop_smt2,
    "config": config_smt2, "setcover": setcover_smt2, "bvcover": bvcover_smt2,
}


def to_smt2(spec: dict) -> str:
    return _SMT2[spec["family"]](spec)
