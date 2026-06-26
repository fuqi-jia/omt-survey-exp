"""Commercial MILP solvers via their NATIVE APIs (no hand-rolled big-M).

Per the credibility requirement, Gurobi and CPLEX are driven through their own
official modelling interfaces, and the job-shop disjunction uses each vendor's
native **indicator constraints** (Gurobi ``addGenConstrIndicator`` / CPLEX
``add_indicator``) rather than a manual big-M. The pure-linear families are
built natively too. These solvers are pluggable: ``available()`` is false unless
the package is importable AND a license yields a usable model, so the framework
auto-skips them where absent (e.g. on the laptop) and uses them on a licensed
server.

NOTE: these adapters are written to each vendor's documented API but cannot be
runtime-tested in an unlicensed environment; validate on first licensed run via
the standard correctness cross-check (objectives must match the other solvers).
"""

from __future__ import annotations

import os
import threading
import time

from .. import SolverResult, _peak_rss_mb
from ..benchmarks.families import jobshop_ops
from ..encodings.milp import MILP_FAMILIES


# =====================================================================
# Gurobi (gurobipy)
# =====================================================================
def _build_gurobi(spec):
    import gurobipy as gp
    from gurobipy import GRB
    fam = spec["family"]
    m = gp.Model()
    m.Params.OutputFlag = 0
    if fam == "gap":
        n, mm, c, w, C = spec["n"], spec["m"], spec["c"], spec["w"], spec["C"]
        x = m.addVars(n, mm, vtype=GRB.BINARY)
        for i in range(n):
            m.addConstr(gp.quicksum(x[i, j] for j in range(mm)) == 1)
        for j in range(mm):
            m.addConstr(gp.quicksum(w[i][j] * x[i, j] for i in range(n)) <= C[j])
        m.setObjective(gp.quicksum(c[i][j] * x[i, j] for i in range(n)
                                   for j in range(mm)), GRB.MINIMIZE)
    elif fam == "knapsack":
        n, R, v, w, C = spec["n"], spec["R"], spec["v"], spec["w"], spec["C"]
        x = m.addVars(n, vtype=GRB.BINARY)
        for r in range(R):
            m.addConstr(gp.quicksum(w[r][i] * x[i] for i in range(n)) <= C[r])
        m.setObjective(gp.quicksum(v[i] * x[i] for i in range(n)), GRB.MAXIMIZE)
    elif fam == "config":
        n, cost, perf, deps, mutex, T = (spec["n"], spec["cost"], spec["perf"],
                                         spec["deps"], spec["mutex"], spec["T"])
        s = m.addVars(n, vtype=GRB.BINARY)
        m.addConstr(gp.quicksum(perf[i] * s[i] for i in range(n)) >= T)
        for (i, j) in deps:
            m.addConstr(s[i] <= s[j])
        for (i, j) in mutex:
            m.addConstr(s[i] + s[j] <= 1)
        m.setObjective(gp.quicksum(cost[i] * s[i] for i in range(n)), GRB.MINIMIZE)
    elif fam == "setcover":
        u, mm, sets, cost = spec["u"], spec["m"], spec["sets"], spec["cost"]
        y = m.addVars(mm, vtype=GRB.BINARY)
        for e in range(u):
            m.addConstr(gp.quicksum(y[j] for j in range(mm) if e in sets[j]) >= 1)
        m.setObjective(gp.quicksum(cost[j] * y[j] for j in range(mm)), GRB.MINIMIZE)
    elif fam == "jobshop":
        ops = jobshop_ops(spec); H = spec["H"]
        dur = {o["id"]: o["dur"] for o in ops}
        st = m.addVars([o["id"] for o in ops], lb=0, ub=H, vtype=GRB.INTEGER)
        mk = m.addVar(lb=0, ub=H, vtype=GRB.INTEGER)
        byjob = {}
        for o in ops:
            byjob.setdefault(o["job"], []).append(o)
        for lst in byjob.values():
            lst.sort(key=lambda o: o["pos"])
            for a, b in zip(lst, lst[1:]):
                m.addConstr(st[b["id"]] >= st[a["id"]] + a["dur"])
        for o in ops:
            m.addConstr(mk >= st[o["id"]] + dur[o["id"]])
        bym = {}
        for o in ops:
            bym.setdefault(o["machine"], []).append(o)
        for lst in bym.values():
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    a, b = lst[i]["id"], lst[j]["id"]
                    y = m.addVar(vtype=GRB.BINARY)
                    # native indicator constraints (no big-M)
                    m.addGenConstrIndicator(y, True, st[a] + dur[a] - st[b] <= 0)
                    m.addGenConstrIndicator(y, False, st[b] + dur[b] - st[a] <= 0)
        m.setObjective(mk, GRB.MINIMIZE)
    else:
        raise ValueError(fam)
    return m


def _opt_gurobi(m, timeout):
    from gurobipy import GRB
    m.Params.Threads = 1
    m.Params.TimeLimit = float(timeout)
    m.optimize()
    proved = m.Status == GRB.OPTIMAL
    obj = m.ObjVal if m.SolCount > 0 else None
    return proved, obj


# =====================================================================
# CPLEX (docplex)
# =====================================================================
def _build_cplex(spec):
    from docplex.mp.model import Model
    fam = spec["family"]
    mdl = Model()
    if fam == "gap":
        n, mm, c, w, C = spec["n"], spec["m"], spec["c"], spec["w"], spec["C"]
        x = mdl.binary_var_matrix(n, mm, "x")
        for i in range(n):
            mdl.add_constraint(mdl.sum(x[i, j] for j in range(mm)) == 1)
        for j in range(mm):
            mdl.add_constraint(mdl.sum(w[i][j] * x[i, j] for i in range(n)) <= C[j])
        mdl.minimize(mdl.sum(c[i][j] * x[i, j] for i in range(n) for j in range(mm)))
    elif fam == "knapsack":
        n, R, v, w, C = spec["n"], spec["R"], spec["v"], spec["w"], spec["C"]
        x = mdl.binary_var_list(n, name="x")
        for r in range(R):
            mdl.add_constraint(mdl.sum(w[r][i] * x[i] for i in range(n)) <= C[r])
        mdl.maximize(mdl.sum(v[i] * x[i] for i in range(n)))
    elif fam == "config":
        n, cost, perf, deps, mutex, T = (spec["n"], spec["cost"], spec["perf"],
                                         spec["deps"], spec["mutex"], spec["T"])
        s = mdl.binary_var_list(n, name="s")
        mdl.add_constraint(mdl.sum(perf[i] * s[i] for i in range(n)) >= T)
        for (i, j) in deps:
            mdl.add_constraint(s[i] <= s[j])
        for (i, j) in mutex:
            mdl.add_constraint(s[i] + s[j] <= 1)
        mdl.minimize(mdl.sum(cost[i] * s[i] for i in range(n)))
    elif fam == "setcover":
        u, mm, sets, cost = spec["u"], spec["m"], spec["sets"], spec["cost"]
        y = mdl.binary_var_list(mm, name="y")
        for e in range(u):
            mdl.add_constraint(mdl.sum(y[j] for j in range(mm) if e in sets[j]) >= 1)
        mdl.minimize(mdl.sum(cost[j] * y[j] for j in range(mm)))
    elif fam == "jobshop":
        ops = jobshop_ops(spec); H = spec["H"]
        dur = {o["id"]: o["dur"] for o in ops}
        st = {o["id"]: mdl.integer_var(0, H, f"st_{o['id']}") for o in ops}
        mk = mdl.integer_var(0, H, "mk")
        byjob = {}
        for o in ops:
            byjob.setdefault(o["job"], []).append(o)
        for lst in byjob.values():
            lst.sort(key=lambda o: o["pos"])
            for a, b in zip(lst, lst[1:]):
                mdl.add_constraint(st[b["id"]] >= st[a["id"]] + a["dur"])
        for o in ops:
            mdl.add_constraint(mk >= st[o["id"]] + dur[o["id"]])
        bym = {}
        for o in ops:
            bym.setdefault(o["machine"], []).append(o)
        for lst in bym.values():
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    a, b = lst[i]["id"], lst[j]["id"]
                    yb = mdl.binary_var()
                    # native indicator constraints (no big-M)
                    mdl.add_indicator(yb, st[a] + dur[a] <= st[b], 1)
                    mdl.add_indicator(yb, st[b] + dur[b] <= st[a], 0)
        mdl.minimize(mk)
    else:
        raise ValueError(fam)
    return mdl


def _opt_cplex(mdl, timeout):
    mdl.context.cplex_parameters.threads = 1
    mdl.set_time_limit(float(timeout))
    sol = mdl.solve()
    if sol is None:
        return False, None
    status = str(mdl.get_solve_status()).lower()
    obj = sol.objective_value
    proved = "optimal" in status and "feasible" not in status
    return proved, obj


# =====================================================================
# Adapters
# =====================================================================
class _NativeMILP:
    paradigm = "milp"

    def applies_to(self, family):
        return family in MILP_FAMILIES

    def _build(self, spec):  # pragma: no cover - overridden
        raise NotImplementedError

    def _optimize(self, model, timeout):  # pragma: no cover - overridden
        raise NotImplementedError

    def _sense(self, family):
        return "max" if family == "knapsack" else "min"

    def solve(self, spec, files, timeout):
        r = SolverResult(solver_name=self.name, paradigm="milp",
                         encoding_name=self.encoding, timeout_s=timeout,
                         sense=self._sense(spec["family"]))
        if not self.applies_to(spec["family"]):
            r.status = "N/A"
            return r
        # ---- build (NOT timed): native lib import + model construction ----
        try:
            model = self._build(spec)
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
            proved, obj = self._optimize(model, timeout)
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
            r.status = "OPTIMAL"; r.proved_optimal = True
            r.objective = int(round(obj))
        elif obj is not None:
            r.status = "SAT"; r.objective = int(round(obj))
        elif dt >= timeout * 0.95:
            r.status = "TIMEOUT"
        else:
            r.status = "UNKNOWN"
        r.finalize_checkpoints()
        return r


class GurobiIndicatorSolver(_NativeMILP):
    name = "gurobi-ind"
    encoding = "native-indicator"

    @staticmethod
    def available():
        try:
            import gurobipy as gp
            m = gp.Model(); m.Params.OutputFlag = 0  # needs a valid license
            return True
        except Exception:
            return False

    def _build(self, spec):
        return _build_gurobi(spec)

    def _optimize(self, model, timeout):
        return _opt_gurobi(model, timeout)


class CplexIndicatorSolver(_NativeMILP):
    name = "cplex-ind"
    encoding = "native-indicator"

    @staticmethod
    def available():
        try:
            from docplex.mp.model import Model
            Model()  # needs CPLEX present
            return True
        except Exception:
            return False

    def _build(self, spec):
        return _build_cplex(spec)

    def _optimize(self, model, timeout):
        return _opt_cplex(model, timeout)
