"""Parametric benchmark families for the three-paradigm comparison.

Each ``spec_*`` function builds ONE structured specification (a plain dict) that
is later turned into four equivalent encodings. Specs are *feasible by
construction* so every instance has a well-defined optimum, and deterministic
given ``(size, seed)`` so the runner can rebuild the in-memory MILP / CP-SAT
models from the manifest without re-reading any file.

Families (derived from the application encodings formalized in survey section 6):

  A  gap        Generalized Assignment   -- pure linear (LIA),  MILP-favoring
  A  knapsack   0-1 multidim. knapsack   -- pure linear (LIA),  MILP-favoring
  B  jobshop    Job-shop scheduling      -- O(n^2) disjunctions, OMT/CP-favoring
  B  config     Feature/system config    -- deps + mutex (regular logic), mixed
  B  setcover   Weighted set cover       -- covering (LIA),     mixed
  C  bvcover    Bit-vector min-cover      -- bit-level (BV),     OMT-only
"""

from __future__ import annotations

import random
from dataclasses import dataclass


# =====================================================================
# Family A1: Generalized Assignment Problem (GAP) -- pure linear (LIA)
#   min  sum_{i,j} c[i][j] x[i][j]
#   s.t. sum_j x[i][j] = 1                (each task assigned once)
#        sum_i w[i][j] x[i][j] <= C[j]    (machine capacity)
#        x[i][j] in {0,1}
# Feasible by construction: round-robin "home" assignment fits in C[j].
# =====================================================================
def spec_gap(n, seed):
    rng = random.Random(seed)
    m = max(2, n // 4)
    c = [[rng.randint(1, 20) for _ in range(m)] for _ in range(n)]
    w = [[rng.randint(1, 10) for _ in range(m)] for _ in range(n)]
    home = [i % m for i in range(n)]
    base = [0] * m
    for i in range(n):
        base[home[i]] += w[i][home[i]]
    C = [base[j] + rng.randint(2, 12) for j in range(m)]
    return {"family": "gap", "n": n, "seed": seed, "m": m, "c": c, "w": w, "C": C}


# =====================================================================
# Family A2: 0-1 multidimensional knapsack -- pure linear (LIA)
#   max sum_i v_i x_i  s.t.  sum_i w[r][i] x_i <= C[r]   (R resource dims)
# Empty set feasible -> optimum always exists.
# =====================================================================
def spec_knapsack(n, seed):
    rng = random.Random(seed)
    R = 2
    v = [rng.randint(1, 20) for _ in range(n)]
    w = [[rng.randint(1, 10) for _ in range(n)] for _ in range(R)]
    C = [max(1, int(0.5 * sum(w[r]))) for r in range(R)]  # ~half capacity
    return {"family": "knapsack", "n": n, "seed": seed, "R": R, "v": v, "w": w, "C": C}


# =====================================================================
# Family B1: Job-shop scheduling -- O(n^2) disjunctions (OMT/CP-favoring)
#   n jobs, one operation per machine in a random machine order;
#   intra-job precedence (chain) + per-machine no-overlap (disjunctive);
#   min makespan.
# =====================================================================
def spec_jobshop(n, seed):
    rng = random.Random(seed)
    m = 3
    jobs = []
    for _ in range(n):
        order = list(range(m))
        rng.shuffle(order)
        jobs.append([(mc, rng.randint(2, 9)) for mc in order])
    H = sum(d for job in jobs for (_, d) in job)  # horizon / big-M
    return {"family": "jobshop", "n": n, "seed": seed, "m": m, "jobs": jobs, "H": H}


def jobshop_ops(s):
    """Flatten a jobshop spec into ops: id, job, pos, machine, dur."""
    ops, oid = [], 0
    for jb, job in enumerate(s["jobs"]):
        for pos, (mc, d) in enumerate(job):
            ops.append({"id": oid, "job": jb, "pos": pos, "machine": mc, "dur": d})
            oid += 1
    return ops


# =====================================================================
# Family B2: Feature/system configuration -- deps + mutex (regular logic)
#   min sum_i cost[i] sel[i]
#   s.t. sum_i perf[i] sel[i] >= T          (coverage)
#        sel[i] => sel[dep[i]]              (dependency chain)
#        sel[i] + sel[k] <= 1               (sparse mutual exclusion)
# Feasible by construction (low coverage threshold, sparse mutex).
# =====================================================================
def spec_config(n, seed):
    rng = random.Random(seed)
    cost = [rng.randint(5, 100) for _ in range(n)]
    perf = [rng.randint(1, 50) for _ in range(n)]
    deps = [(i, i + 1) for i in range(0, n - 1, 2)]
    mutex = [(i, min(i + 2, n - 1)) for i in range(0, n - 1, 5) if i + 2 < n]
    T = sum(perf) // 4
    return {"family": "config", "n": n, "seed": seed, "cost": cost,
            "perf": perf, "deps": deps, "mutex": mutex, "T": T}


# =====================================================================
# Family B3: Weighted set cover -- covering (LIA)
#   min sum_j cost_j y_j  s.t.  every element covered by >=1 chosen set
# Feasible by construction: every element belongs to >=1 set.
# =====================================================================
def spec_setcover(n, seed):
    rng = random.Random(seed)
    u = n
    m = max(3, n // 2)
    sets = []
    for _ in range(m):
        k = rng.randint(1, max(2, u // 3))
        sets.append(set(rng.sample(range(u), k)))
    for e in range(u):
        if not any(e in S for S in sets):
            sets[rng.randrange(m)].add(e)
    sets = [sorted(S) for S in sets]
    cost = [rng.randint(1, 20) for _ in range(m)]
    return {"family": "setcover", "n": n, "seed": seed, "u": u, "m": m,
            "sets": sets, "cost": cost}


# =====================================================================
# Family C: Bit-vector min-cover -- OMT(BV)-only
#   minimize unsigned value of x in BV_w
#   s.t. (x bvand clause_k) != 0       (cover each clause)
#        (x bvand forbidden) = 0       (avoid forbidden bits)
# Feasible by construction: each clause contains an allowed bit.
# =====================================================================
def spec_bvcover(w, seed):
    rng = random.Random(seed)
    forbidden = 0
    for b in range(w):
        if rng.random() < 0.25:
            forbidden |= (1 << b)
    allowed = [b for b in range(w) if not (forbidden >> b) & 1]
    nclauses = max(2, w // 2)
    clauses = []
    for _ in range(nclauses):
        mask = 0
        kbits = rng.sample(range(w), k=max(1, w // 4))
        for b in kbits:
            mask |= (1 << b)
        guaranteed = rng.choice(allowed)
        mask |= (1 << guaranteed)
        clauses.append(mask)
    return {"family": "bvcover", "n": w, "seed": seed, "w": w,
            "forbidden": forbidden, "clauses": clauses}


# =====================================================================
# Registry + metadata
# =====================================================================
@dataclass(frozen=True)
class FamilyMeta:
    key: str
    category: str          # A / B / C
    sense: str             # min / max
    paradigms: tuple       # which paradigms apply
    desc: str


FAMILIES = {
    "gap":      FamilyMeta("gap", "A", "min", ("omt", "milp", "cp"),
                           "Generalized assignment (pure linear, LIA)"),
    "knapsack": FamilyMeta("knapsack", "A", "max", ("omt", "milp", "cp"),
                           "0-1 multidim. knapsack (pure linear, LIA)"),
    "jobshop":  FamilyMeta("jobshop", "B", "min", ("omt", "milp", "cp"),
                           "Job-shop scheduling (O(n^2) disjunctions, LIA)"),
    "config":   FamilyMeta("config", "B", "min", ("omt", "milp", "cp"),
                           "System configuration (deps + mutex, LIA)"),
    "setcover": FamilyMeta("setcover", "B", "min", ("omt", "milp", "cp"),
                           "Weighted set cover (covering, LIA)"),
    "bvcover":  FamilyMeta("bvcover", "C", "min", ("omt",),
                           "Bit-vector min-cover (bit-level, BV)"),
}

_SPECS = {
    "gap": spec_gap, "knapsack": spec_knapsack, "jobshop": spec_jobshop,
    "config": spec_config, "setcover": spec_setcover, "bvcover": spec_bvcover,
}


def build(family: str, size: int, seed: int) -> dict:
    """Rebuild the structured spec for an instance (deterministic)."""
    return _SPECS[family](size, seed)
