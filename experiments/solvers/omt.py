"""OMT solver adapters: nuZ (Z3) and OptiMathSAT, both driven via SMT-LIB2 files.

Both parse the objective uniformly from the ``(__obj <value>)`` line that
``(get-objectives)`` prints. Z3 needs no flags; OptiMathSAT needs
``-optimization=TRUE`` on the command line (and ``:produce-models true`` in the
file, which the encoder already emits). The local PATH ``optimathsat`` ships
*without* optimization, so we prefer the repo-local 1.7.4 binary under tools/.
"""

from __future__ import annotations

import os
import re
import shutil

from .. import SolverResult, smt_value_to_int, stream_run

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# (__obj <int | #x.. | #b.. | (_ bvN w)>)
_OBJ_RE = re.compile(
    r"\(\s*__obj\s+(#x[0-9a-fA-F]+|#b[01]+|\(_\s*bv\d+\s+\d+\)|-?\d+)\s*\)"
)


def _parse_obj(text: str):
    m = _OBJ_RE.search(text)
    return smt_value_to_int(m.group(1)) if m else None


def _classify(text: str):
    """Return coarse SMT status token found in solver output."""
    if re.search(r"\bunsat\b", text):
        return "unsat"
    if re.search(r"\bsat\b", text):
        return "sat"
    return None


class _OMTSolver:
    paradigm = "omt"

    def __init__(self, name, sense_lookup):
        self.name = name
        self._sense_lookup = sense_lookup

    def _cmd(self, smt2_path, timeout):  # pragma: no cover - overridden
        raise NotImplementedError

    def solve(self, spec, files, timeout):
        smt2 = files["smt2"]
        sense = self._sense_lookup(spec["family"])
        r = SolverResult(solver_name=self.name, paradigm="omt",
                         encoding_name="smt2", timeout_s=timeout, sense=sense)
        run = stream_run(self._cmd(smt2, timeout), timeout)
        r.runtime_s = round(run["elapsed"], 4)
        r.memory_peak_mb = round(run["peak_mb"], 2)
        out = run["out"]
        obj = _parse_obj(out)
        cls = _classify(out)
        # OptiMathSAT marks an incomplete search ("partial search") and may emit
        # (error ...) (e.g. "non-integer model value" on some integer-maximize
        # instances). In both cases the reported value is a feasible incumbent,
        # NOT a proven optimum -- never count it as optimal.
        incomplete = ("partial search" in out) or ("(error" in out)
        if run["timed_out"] and obj is None:
            r.status = "TIMEOUT"
        elif cls == "unsat":
            r.status = "UNSAT"
        elif obj is not None:
            r.objective = obj
            proved = not run["timed_out"] and not incomplete
            r.status = "OPTIMAL" if proved else "SAT"
            r.proved_optimal = proved
            if incomplete:
                r.error_message = "incomplete search (partial/error)"
        elif cls == "sat":
            r.status = "SAT"
        else:
            r.status = "ERROR"
            r.error_message = out.strip()[-300:]
        r.finalize_checkpoints()
        return r


class Z3Solver(_OMTSolver):
    def __init__(self, sense_lookup):
        super().__init__("z3", sense_lookup)

    @staticmethod
    def available():
        return shutil.which("z3") is not None

    def _cmd(self, smt2_path, timeout):
        # -T: soft per-call wall-clock timeout (seconds) so z3 self-terminates.
        return ["z3", f"-T:{max(1, int(timeout))}", smt2_path]


class OptiMathSATSolver(_OMTSolver):
    def __init__(self, sense_lookup):
        super().__init__("optimathsat", sense_lookup)

    @staticmethod
    def _binary():
        """Prefer the repo-local 1.7.4 build; fall back to PATH only if it
        actually supports optimization."""
        local = os.path.join(
            _REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin", "optimathsat"
        )
        if os.path.exists(local):
            return local
        path = shutil.which("optimathsat")
        return path

    @classmethod
    def available(cls):
        b = cls._binary()
        if not b:
            return False
        # verify it supports optimization (the PATH build often does not)
        import subprocess
        try:
            probe = ("(set-option :produce-models true)(set-logic QF_LIA)"
                     "(declare-fun x () Int)(assert (>= x 1))(minimize x)"
                     "(check-sat)(get-objectives)")
            out = subprocess.run([b, "-optimization=TRUE"], input=probe,
                                 capture_output=True, text=True, timeout=15)
            return "not supported" not in (out.stdout + out.stderr)
        except Exception:
            return False

    def _cmd(self, smt2_path, timeout):
        return [self._binary(), "-optimization=TRUE", smt2_path]
