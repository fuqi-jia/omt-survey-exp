"""Open MILP solvers on the recognized Pyomo.GDP encodings (big-M / hull).

One adapter per (backend, transform): e.g. ``highs-bigm``, ``cbc-bigm``,
``scip-bigm``, ``highs-hull``. All consume the same Pyomo GDP model
(``encodings.milp_gdp``); the transform decides big-M vs convex-hull. Applies
only to the disjunctive family (job-shop).

Timing discipline: only the solver's *optimize* call is timed. Library import,
model construction, the GDP transformation, and (for SCIP) the LP export all
happen BEFORE the clock starts -- otherwise the (large) cold ``import pyomo``
under subprocess isolation would dwarf the actual solve and make the comparison
meaningless. This matches the other adapters, which also time only the solve.

Backends:
  highs -> Pyomo APPSI Highs (highspy)
  cbc   -> Pyomo SolverFactory('cbc') with PuLP's bundled cbc binary
  scip  -> pyscipopt reading the Pyomo-exported .lp
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

from .. import SolverResult, _peak_rss_mb
from ..encodings.milp_gdp import GDP_FAMILIES, build_transformed


def _cbc_path():
    try:
        import pulp
        return pulp.apis.PULP_CBC_CMD().path
    except Exception:
        return None


# ---- per backend: prep (untimed) returns ctx; run (timed) -> (proved, obj) ----
def _prep_highs(m, timeout):
    from pyomo.contrib.appsi.solvers import Highs
    opt = Highs()
    opt.config.time_limit = float(timeout)
    opt.config.load_solution = False
    try:
        opt.highs_options = {"threads": 1}
    except Exception:
        pass
    return ("highs", opt, m)


def _prep_cbc(m, timeout):
    import pyomo.environ as pyo
    opt = pyo.SolverFactory("cbc", executable=_cbc_path())
    opt.options["seconds"] = float(timeout)
    opt.options["threads"] = 1
    return ("factory", opt, m)


def _prep_gurobi(m, timeout):
    import pyomo.environ as pyo
    opt = pyo.SolverFactory("gurobi_direct")
    opt.options["TimeLimit"] = float(timeout)
    opt.options["Threads"] = 1
    return ("factory", opt, m)


def _prep_cplex(m, timeout):
    import pyomo.environ as pyo
    opt = pyo.SolverFactory("cplex_direct")
    opt.options["timelimit"] = float(timeout)
    opt.options["threads"] = 1
    return ("factory", opt, m)


def _prep_scip(m, timeout):
    from pyscipopt import Model
    lp = os.path.join(tempfile.gettempdir(), f"gdp_{os.getpid()}_{id(m)}.lp")
    m.write(lp, io_options={"symbolic_solver_labels": True})
    sm = Model()
    sm.hideOutput()
    sm.readProblem(lp)
    sm.setParam("limits/time", float(timeout))
    return ("scip", sm, lp)


def _run(ctx):
    kind = ctx[0]
    if kind == "highs":
        _, opt, m = ctx
        res = opt.solve(m)
        tc = str(res.termination_condition).split(".")[-1].lower()
        return tc == "optimal", res.best_feasible_objective
    if kind == "factory":  # cbc / gurobi_direct / cplex_direct
        import pyomo.environ as pyo
        _, opt, m = ctx
        try:
            r = opt.solve(m, tee=False, load_solutions=True)
            tc = str(r.solver.termination_condition).lower()
            obj = pyo.value(m.obj)
        except Exception:
            return False, None
        return ("optimal" in tc and "subopt" not in tc), obj
    if kind == "scip":
        _, sm, lp = ctx
        sm.optimize()
        status = sm.getStatus()
        obj = sm.getObjVal() if sm.getNSols() > 0 else None
        try:
            os.remove(lp)
        except Exception:
            pass
        return status == "optimal", obj
    raise ValueError(kind)


_PREP = {"highs": _prep_highs, "cbc": _prep_cbc, "scip": _prep_scip,
         "gurobi": _prep_gurobi, "cplex": _prep_cplex}


class PyomoGDPSolver:
    paradigm = "milp"

    def __init__(self, backend, transform):
        self.backend = backend
        self.transform = transform
        self.name = f"{backend}-{transform}"

    def applies_to(self, family):
        return family in GDP_FAMILIES

    @staticmethod
    def backend_available(backend):
        try:
            if backend == "highs":
                from pyomo.contrib.appsi.solvers import Highs
                return Highs().available()
            if backend == "cbc":
                return _cbc_path() is not None
            if backend == "scip":
                import pyscipopt  # noqa: F401
                return True
            if backend in ("gurobi", "cplex"):
                import pyomo.environ as pyo
                fac = "gurobi_direct" if backend == "gurobi" else "cplex_direct"
                return pyo.SolverFactory(fac).available(exception_flag=False)
        except Exception:
            return False
        return False

    def solve(self, spec, files, timeout):
        r = SolverResult(solver_name=self.name, paradigm="milp",
                         encoding_name=f"gdp-{self.transform}",
                         timeout_s=timeout, sense="min")
        if spec["family"] not in GDP_FAMILIES:
            r.status = "N/A"
            return r

        # ---- prepare (NOT timed): import + build + transform + backend setup ----
        try:
            import pyomo.environ  # noqa: F401  (warm the heavy cold import)
            m = build_transformed(spec, self.transform)
            ctx = _PREP[self.backend](m, timeout)
        except Exception as e:
            r.status = "ERROR"
            r.error_message = str(e)[-300:]
            return r

        # ---- timed: only the optimize call ----
        stop = threading.Event()
        mem = {"peak_mb": 0.0}
        mon = threading.Thread(target=_peak_rss_mb,
                               args=(os.getpid(), stop, mem), daemon=True)
        mon.start()
        t0 = time.perf_counter()
        try:
            proved, obj = _run(ctx)
            err = None
        except Exception as e:
            proved, obj, err = False, None, str(e)
        finally:
            dt = time.perf_counter() - t0
            stop.set()
            mon.join(timeout=2.0)

        r.runtime_s = round(dt, 4)
        r.memory_peak_mb = round(mem.get("peak_mb", 0.0), 2)
        if err is not None:
            r.status = "ERROR"
            r.error_message = err[-300:]
        elif proved and obj is not None:
            r.status = "OPTIMAL"
            r.proved_optimal = True
            r.objective = int(round(obj))
        elif obj is not None:
            r.status = "SAT"
            r.objective = int(round(obj))
        elif dt >= timeout * 0.95:
            r.status = "TIMEOUT"
        else:
            r.status = "UNKNOWN"
        r.finalize_checkpoints()
        return r
