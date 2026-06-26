"""Solver registry: discover which OMT / MILP / CP backends are usable here.

``detect_solvers()`` returns ready-to-use adapter instances in a stable order
(OMT, then MILP, then CP). Each adapter exposes ``.name``, ``.paradigm`` and
``.solve(spec, files, timeout) -> SolverResult``. Backends that are absent
(OptiMathSAT without optimization, Gurobi/CPLEX without a license, Chuffed not
installed) are silently skipped so the same code runs on a laptop and a server.
"""

from __future__ import annotations

from ..benchmarks.families import FAMILIES
from .omt import Z3Solver, OptiMathSATSolver
from .milp import MILPSolver, available_milp_keys
from .cp import GecodeSolver, ChuffedSolver, CPSATSolver


def _sense(family: str) -> str:
    return FAMILIES[family].sense


# desired ordering of MILP backends when present
_MILP_ORDER = ["cbc", "highs", "scip", "gurobi", "cplex"]


def detect_solvers(want=None):
    """Return available solver adapter instances.

    ``want`` (optional iterable of names) restricts to that subset.
    """
    out = []
    # ---- OMT ----
    if Z3Solver.available():
        out.append(Z3Solver(_sense))
    if OptiMathSATSolver.available():
        out.append(OptiMathSATSolver(_sense))
    # ---- MILP ----
    have = set(available_milp_keys())
    for key in _MILP_ORDER:
        if key in have:
            out.append(MILPSolver(key))
    # ---- CP ----
    if GecodeSolver.available():
        out.append(GecodeSolver(_sense))
    if ChuffedSolver.available():
        out.append(ChuffedSolver(_sense))
    if CPSATSolver.available():
        out.append(CPSATSolver(_sense))

    if want is not None:
        want = set(want)
        out = [s for s in out if s.name in want]
    return out


def all_solver_names():
    return [s.name for s in detect_solvers()]
