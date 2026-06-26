"""MILP disjunction encoding via Pyomo.GDP (recognized, not hand-rolled).

The job-shop no-overlap is a genuine disjunction. Instead of hand-writing the
big-M, we declare it with ``pyomo.gdp.Disjunction`` and let Pyomo's recognized
transformations generate the MILP:

  * ``gdp.bigm``  -- the textbook big-M reformulation
  * ``gdp.hull``  -- the (tighter) convex-hull / extended reformulation

This is the credible source for the "big-M" data point: the reformulation comes
from an established framework, and the same Pyomo model is fed to every open
MILP backend (CBC / HiGHS / SCIP). Only the disjunctive family is modelled here;
the pure-linear families have no encoding choice and stay on the direct model.
"""

from __future__ import annotations

from ..benchmarks.families import jobshop_ops

# only families with a genuine disjunction need a GDP encoding
GDP_FAMILIES = frozenset({"jobshop"})
TRANSFORMS = ("bigm", "hull")


def build_gdp_jobshop(spec):
    """Return an untransformed Pyomo GDP model for a job-shop instance."""
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunction

    ops = jobshop_ops(spec)
    H = spec["H"]
    dur = {o["id"]: o["dur"] for o in ops}
    ids = [o["id"] for o in ops]

    m = pyo.ConcreteModel()
    m.st = pyo.Var(ids, domain=pyo.NonNegativeIntegers, bounds=(0, H))
    m.mk = pyo.Var(domain=pyo.NonNegativeIntegers, bounds=(0, H))
    m.c = pyo.ConstraintList()

    # intra-job precedence
    byjob = {}
    for o in ops:
        byjob.setdefault(o["job"], []).append(o)
    for lst in byjob.values():
        lst.sort(key=lambda o: o["pos"])
        for a, b in zip(lst, lst[1:]):
            m.c.add(m.st[b["id"]] >= m.st[a["id"]] + a["dur"])
    # makespan
    for o in ops:
        m.c.add(m.mk >= m.st[o["id"]] + dur[o["id"]])

    # per-machine no-overlap as native disjunctions
    bym = {}
    for o in ops:
        bym.setdefault(o["machine"], []).append(o)
    pairs = [(lst[i]["id"], lst[j]["id"])
             for lst in bym.values()
             for i in range(len(lst)) for j in range(i + 1, len(lst))]
    m.P = pyo.Set(initialize=range(len(pairs)))

    def _disj(mm, k):
        a, b = pairs[k]
        return [[mm.st[a] + dur[a] <= mm.st[b]],
                [mm.st[b] + dur[b] <= mm.st[a]]]

    m.disj = Disjunction(m.P, rule=_disj)
    m.obj = pyo.Objective(expr=m.mk)
    return m


def build_transformed(spec, transform="bigm"):
    """Build the GDP model and apply ``gdp.<transform>`` in place."""
    import pyomo.environ as pyo
    if transform not in TRANSFORMS:
        raise ValueError(transform)
    m = build_gdp_jobshop(spec)
    pyo.TransformationFactory(f"gdp.{transform}").apply_to(m)
    return m
