"""Core data model and execution helpers for the OMT survey experiment.

This package implements a *single-source-of-truth* three-paradigm comparison:
every benchmark instance is described by ONE structured spec from which we emit
four provably-equivalent encodings (OMT / MILP / CP-MiniZinc / CP-SAT). Solver
adapters consume those encodings and return a uniform :class:`SolverResult`.

The two non-obvious pieces live here:

* :class:`SolverResult` -- the uniform record every adapter returns, including
  ``anytime`` incumbent trajectory and the 10/30/60 s checkpoint scalars.
* :func:`stream_run` -- run a CLI solver as a subprocess while (a) reading its
  stdout line-by-line with wall-clock timestamps so improving incumbents can be
  captured, and (b) polling peak RSS of the whole child process tree.

Everything is dependency-light at import time: heavy/optional backends
(``pulp``, ``ortools``, ``pyscipopt`` ...) are imported lazily inside the
adapters so this package imports cleanly even on a machine missing them.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

# Wall-clock checkpoints (seconds) at which we snapshot the best incumbent.
CHECKPOINTS = (10.0, 30.0, 60.0)


# =====================================================================
# Uniform result record
# =====================================================================
@dataclass
class SolverResult:
    """Standardized result returned by every solver adapter.

    ``status`` is the *coarse* outcome; ``proved_optimal`` is the bit that the
    correctness cross-check and the solved/total tables rely on.

    status in {OPTIMAL, SAT, UNSAT, TIMEOUT, ERROR, UNKNOWN}
    """

    status: str = "UNKNOWN"
    proved_optimal: bool = False
    objective: Optional[float] = None
    runtime_s: float = 0.0
    memory_peak_mb: float = 0.0
    # anytime: full (t_seconds, incumbent_objective) trajectory, plus the
    # three checkpoint scalars derived from it (best objective known by t).
    incumbents: list = field(default_factory=list)
    best_at_10s: Optional[float] = None
    best_at_30s: Optional[float] = None
    best_at_60s: Optional[float] = None
    sense: str = "min"  # "min" or "max" -- needed to reduce incumbents correctly
    solution: Any = None
    error_message: Optional[str] = None
    # identification (filled by the runner)
    solver_name: str = ""
    paradigm: str = ""
    encoding_name: str = ""
    family: str = ""
    category: str = ""
    instance: str = ""
    size: int = 0
    seed: int = 0
    timeout_s: float = 60.0
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )

    def finalize_checkpoints(self) -> None:
        """Derive best_at_{10,30,60}s from the incumbent trajectory.

        If the solver streamed incumbents we use them directly. Otherwise we
        fall back to the coarse rule: a solution found at total runtime ``t`` is
        known from ``t`` onward, so it counts for every checkpoint >= t.
        """
        traj = list(self.incumbents)
        if not traj and self.objective is not None and self.status in ("OPTIMAL", "SAT"):
            traj = [(self.runtime_s, self.objective)]
        better = min if self.sense == "min" else max
        for ck, attr in zip(CHECKPOINTS, ("best_at_10s", "best_at_30s", "best_at_60s")):
            vals = [obj for (t, obj) in traj if t <= ck and obj is not None]
            if vals:
                setattr(self, attr, better(vals))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


# =====================================================================
# Subprocess execution with timestamped incumbent capture + peak RSS
# =====================================================================
def _peak_rss_mb(pid: int, stop: threading.Event, out: dict) -> None:
    """Poll the RSS of ``pid`` and its children until ``stop`` is set."""
    try:
        import psutil
    except ImportError:
        return
    try:
        proc = psutil.Process(pid)
    except Exception:
        return
    peak = 0.0
    while not stop.is_set():
        try:
            rss = proc.memory_info().rss
            for ch in proc.children(recursive=True):
                try:
                    rss += ch.memory_info().rss
                except Exception:
                    pass
            peak = max(peak, rss)
        except Exception:
            break
        stop.wait(0.05)
    out["peak_mb"] = peak / (1024 * 1024)


def stream_run(
    cmd: list[str],
    timeout: float,
    incumbent_parser: Optional[Callable[[str], Optional[float]]] = None,
    grace: float = 10.0,
) -> dict:
    """Run ``cmd`` capturing stdout/stderr, timestamped incumbents, and peak RSS.

    Returns a dict with keys: out (combined text), incumbents (list of
    ``[t, obj]``), elapsed (float), peak_mb (float), timed_out (bool).

    ``incumbent_parser`` maps a single stdout line to an objective value (or
    None). Each match is timestamped with the wall-clock offset at the moment
    the line is read -- a good proxy for when the solver found that incumbent.
    """
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # own process group -> clean kill of children
    )
    stop = threading.Event()
    mem: dict = {"peak_mb": 0.0}
    mon = threading.Thread(target=_peak_rss_mb, args=(proc.pid, stop, mem), daemon=True)
    mon.start()

    lines: list[str] = []
    incs: list[list] = []
    timed_out = False

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                if incumbent_parser is not None:
                    obj = incumbent_parser(line)
                    if obj is not None:
                        incs.append([round(time.perf_counter() - t0, 4), obj])
        except Exception:
            pass

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
    reader.join(timeout=grace)
    elapsed = time.perf_counter() - t0
    stop.set()
    mon.join(timeout=2.0)
    return {
        "out": "".join(lines),
        "incumbents": incs,
        "elapsed": elapsed,
        "peak_mb": mem.get("peak_mb", 0.0),
        "timed_out": timed_out,
    }


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# convenience: SMT-LIB / MiniZinc objective literals -------------------
def smt_value_to_int(tok: str) -> int:
    """Parse an SMT-LIB integer or bit-vector literal to a Python int."""
    tok = tok.strip()
    if tok.startswith("#x"):
        return int(tok[2:], 16)
    if tok.startswith("#b"):
        return int(tok[2:], 2)
    m = re.match(r"\(_\s+bv(\d+)\s+\d+\)", tok)  # (_ bvN width)
    if m:
        return int(m.group(1))
    return int(tok)
