"""CP solver adapters: Gecode & Chuffed (MiniZinc CLI) and OR-Tools CP-SAT.

The MiniZinc adapters stream improving solutions (``--intermediate-solutions``)
which we timestamp on read to build the anytime curve; CP-SAT uses a native
solution callback. All run single-threaded (``-p 1`` / ``num_search_workers=1``)
for a fair comparison with the single-threaded OMT/MILP runs.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time

from .. import SolverResult, _peak_rss_mb, stream_run
from ..encodings.minizinc import CP_FAMILIES
from ..encodings.cpsat import CPSAT_FAMILIES, build_cpsat

_MZN_OBJ = re.compile(r"_objective\s*=\s*(-?\d+)")


def minizinc_has(name: str) -> bool:
    if not shutil.which("minizinc"):
        return False
    try:
        out = subprocess.run(["minizinc", "--solvers"], capture_output=True,
                             text=True, timeout=20).stdout.lower()
    except Exception:
        return False
    return name in out


class _MiniZincSolver:
    paradigm = "cp"

    def __init__(self, name, sense_lookup):
        self.name = name
        self._sense_lookup = sense_lookup

    def solve(self, spec, files, timeout):
        sense = self._sense_lookup(spec["family"])
        r = SolverResult(solver_name=self.name, paradigm="cp",
                         encoding_name="minizinc", timeout_s=timeout, sense=sense)
        if spec["family"] not in CP_FAMILIES or "mzn" not in files:
            r.status = "N/A"
            return r
        cmd = ["minizinc", "--solver", self.name, "-p", "1",
               "--output-objective", "--intermediate-solutions",
               "--time-limit", str(int(timeout * 1000)), files["mzn"]]
        run = stream_run(cmd, timeout + 8,
                         incumbent_parser=lambda ln: (
                             int(_MZN_OBJ.search(ln).group(1))
                             if _MZN_OBJ.search(ln) else None))
        r.runtime_s = round(min(run["elapsed"], timeout), 4)
        r.memory_peak_mb = round(run["peak_mb"], 2)
        r.incumbents = run["incumbents"]
        out = run["out"]
        best = None
        if r.incumbents:
            vals = [o for _, o in r.incumbents]
            best = min(vals) if sense == "min" else max(vals)
        if "=====UNSATISFIABLE=====" in out:
            r.status = "UNSAT"
        elif "==========" in out and best is not None:
            r.status = "OPTIMAL"
            r.proved_optimal = True
            r.objective = best
        elif best is not None:
            r.status = "SAT"
            r.objective = best
        elif run["timed_out"]:
            r.status = "TIMEOUT"
        else:
            r.status = "ERROR"
            r.error_message = out.strip()[-300:]
        r.finalize_checkpoints()
        return r


class GecodeSolver(_MiniZincSolver):
    def __init__(self, sense_lookup):
        super().__init__("gecode", sense_lookup)

    @staticmethod
    def available():
        return minizinc_has("gecode")


class ChuffedSolver(_MiniZincSolver):
    def __init__(self, sense_lookup):
        super().__init__("chuffed", sense_lookup)

    @staticmethod
    def available():
        return minizinc_has("chuffed")


class CPSATSolver:
    paradigm = "cp"
    name = "cpsat"

    def __init__(self, sense_lookup):
        self._sense_lookup = sense_lookup

    @staticmethod
    def available():
        try:
            from ortools.sat.python import cp_model  # noqa: F401
            return True
        except Exception:
            return False

    def solve(self, spec, files, timeout):
        from ortools.sat.python import cp_model
        sense = self._sense_lookup(spec["family"])
        r = SolverResult(solver_name=self.name, paradigm="cp",
                         encoding_name="cpsat", timeout_s=timeout, sense=sense)
        if spec["family"] not in CPSAT_FAMILIES:
            r.status = "N/A"
            return r
        md, obj, _ = build_cpsat(spec)

        class _Rec(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.incs = []

            def on_solution_callback(self):
                self.incs.append([round(self.WallTime(), 4),
                                  int(self.Value(obj))])

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(timeout)
        solver.parameters.num_search_workers = 1
        rec = _Rec()

        stop = threading.Event()
        mem: dict = {"peak_mb": 0.0}
        mon = threading.Thread(target=_peak_rss_mb,
                               args=(os.getpid(), stop, mem), daemon=True)
        mon.start()
        t0 = time.perf_counter()
        try:
            status = solver.Solve(md, rec)
            err = None
        except Exception as e:
            status, err = None, str(e)
        finally:
            dt = time.perf_counter() - t0
            stop.set()
            mon.join(timeout=2.0)

        r.runtime_s = round(dt, 4)
        r.memory_peak_mb = round(mem.get("peak_mb", 0.0), 2)
        r.incumbents = rec.incs
        if err is not None:
            r.status = "ERROR"
            r.error_message = err[-300:]
            return r
        if status == cp_model.OPTIMAL:
            r.status = "OPTIMAL"
            r.proved_optimal = True
            r.objective = int(round(solver.ObjectiveValue()))
        elif status == cp_model.FEASIBLE:
            r.status = "SAT"
            r.objective = int(round(solver.ObjectiveValue()))
        elif status == cp_model.INFEASIBLE:
            r.status = "UNSAT"
        else:
            r.status = "TIMEOUT"
        r.finalize_checkpoints()
        return r
