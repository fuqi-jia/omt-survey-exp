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
from .milp_pyomo import PyomoGDPSolver
from .milp_indicator import GurobiIndicatorSolver, CplexIndicatorSolver
from .cp import GecodeSolver, ChuffedSolver, CPSATSolver


def _sense(family: str) -> str:
    return FAMILIES[family].sense


# MILP backends usable via PuLP on the pure-linear families
_MILP_ORDER = ["cbc", "highs", "scip"]
# backends that solve the recognized Pyomo.GDP job-shop big-M encoding.
# gurobi/cplex here give big-M on the SAME commercial engine as the *-ind
# adapters -> a clean "big-M vs native indicator" contrast per solver.
_GDP_BACKENDS = ["cbc", "highs", "scip", "gurobi", "cplex"]


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
    # ---- MILP: pure-linear families via PuLP direct models ----
    have = set(available_milp_keys())
    for key in _MILP_ORDER:
        if key in have:
            out.append(MILPSolver(key))
    # ---- MILP: disjunctive family via recognized Pyomo.GDP encodings ----
    for be in _GDP_BACKENDS:
        if PyomoGDPSolver.backend_available(be):
            out.append(PyomoGDPSolver(be, "bigm"))
    if PyomoGDPSolver.backend_available("highs"):     # big-M vs hull contrast
        out.append(PyomoGDPSolver("highs", "hull"))
    # ---- MILP: commercial solvers via native APIs (indicator constraints) ----
    if GurobiIndicatorSolver.available():
        out.append(GurobiIndicatorSolver())
    if CplexIndicatorSolver.available():
        out.append(CplexIndicatorSolver())
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


def make_solver(name):
    """Construct a single adapter by name WITHOUT probing the others.

    Used by the subprocess worker (run_all --solve-one) so each isolated solve
    pays no detection cost. Mirrors the names produced by detect_solvers().
    """
    if name == "z3":
        return Z3Solver(_sense)
    if name == "optimathsat":
        return OptiMathSATSolver(_sense)
    if name in ("cbc", "highs", "scip"):
        return MILPSolver(name)
    if name.endswith("-bigm") or name.endswith("-hull"):
        backend, transform = name.rsplit("-", 1)
        return PyomoGDPSolver(backend, transform)
    if name == "gurobi-ind":
        return GurobiIndicatorSolver()
    if name == "cplex-ind":
        return CplexIndicatorSolver()
    if name == "gecode":
        return GecodeSolver(_sense)
    if name == "chuffed":
        return ChuffedSolver(_sense)
    if name == "cpsat":
        return CPSATSolver(_sense)
    raise ValueError(f"unknown solver name: {name}")
