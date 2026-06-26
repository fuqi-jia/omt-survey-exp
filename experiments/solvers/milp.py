"""MILP solver adapters via PuLP: CBC, HiGHS, SCIP, and (pluggable) Gurobi/CPLEX.

All consume the same big-M PuLP model built by ``encodings.milp``. PuLP does not
surface streaming incumbents, so the anytime trajectory is left empty and the
coarse "solution known from total runtime onward" rule applies; the headline
metrics (proven-optimal status, objective, wall-clock, peak RSS) are exact.

Peak RSS is polled on this process *and its children* during the solve: CBC runs
as a child subprocess while HiGHS/SCIP run in-process, so both are captured.
"""

from __future__ import annotations

import threading
import time

from .. import SolverResult, _peak_rss_mb
from ..encodings.milp import MILP_FAMILIES, to_pulp


def _make_solver(key, timeout):
    import pulp
    t = max(1, int(timeout))
    if key == "cbc":
        return pulp.PULP_CBC_CMD(msg=0, timeLimit=t, threads=1)
    if key == "highs":
        return pulp.HiGHS(msg=False, timeLimit=t, threads=1)
    if key == "scip":
        return pulp.SCIP_PY(msg=False, timeLimit=t)
    if key == "gurobi":
        return pulp.GUROBI(msg=0, timeLimit=t, threads=1)
    if key == "cplex":
        return pulp.CPLEX_PY(msg=0, timeLimit=t)
    raise ValueError(key)


# PuLP backend name -> our short key
_PULP_NAME = {
    "PULP_CBC_CMD": "cbc", "HiGHS": "highs", "HiGHS_CMD": "highs",
    "SCIP_PY": "scip", "SCIP_CMD": "scip",
    "GUROBI": "gurobi", "GUROBI_CMD": "gurobi",
    "CPLEX_PY": "cplex", "CPLEX_CMD": "cplex",
}


def available_milp_keys():
    """Short keys of MILP backends actually usable on this machine."""
    try:
        import pulp
    except ImportError:
        return []
    keys, seen = [], set()
    for name in pulp.listSolvers(onlyAvailable=True):
        k = _PULP_NAME.get(name)
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


class MILPSolver:
    paradigm = "milp"

    def __init__(self, key):
        self.name = key

    def solve(self, spec, files, timeout):
        import pulp
        r = SolverResult(solver_name=self.name, paradigm="milp",
                         encoding_name="pulp", timeout_s=timeout, sense="min")
        if spec["family"] not in MILP_FAMILIES:
            r.status = "N/A"
            return r
        prob = to_pulp(spec)
        solver = _make_solver(self.name, timeout)

        stop = threading.Event()
        mem: dict = {"peak_mb": 0.0}
        import os
        mon = threading.Thread(target=_peak_rss_mb,
                               args=(os.getpid(), stop, mem), daemon=True)
        mon.start()
        t0 = time.perf_counter()
        try:
            prob.solve(solver)
            err = None
        except Exception as e:  # backend missing / license / runtime failure
            err = str(e)
        finally:
            dt = time.perf_counter() - t0
            stop.set()
            mon.join(timeout=2.0)

        r.runtime_s = round(dt, 4)
        r.memory_peak_mb = round(mem.get("peak_mb", 0.0), 2)
        if err is not None:
            r.status = "ERROR"
            r.error_message = err[-300:]
            return r

        status = prob.status                # LpStatus*
        sol_status = getattr(prob, "sol_status", None)  # LpSolution*
        val = pulp.value(prob.objective)
        proved = (status == pulp.LpStatusOptimal
                  and sol_status == pulp.constants.LpSolutionOptimal)
        feasible = (val is not None and sol_status in
                    (pulp.constants.LpSolutionOptimal,
                     pulp.constants.LpSolutionIntegerFeasible))
        if status == pulp.LpStatusInfeasible:
            r.status = "UNSAT"
        elif proved:
            r.status = "OPTIMAL"
            r.proved_optimal = True
            r.objective = int(round(val))
        elif feasible:
            r.status = "SAT"
            r.objective = int(round(val))
        elif dt >= timeout * 0.95:
            r.status = "TIMEOUT"
        else:
            r.status = "UNKNOWN"
        r.finalize_checkpoints()
        return r
