# Experiment design

## Goal

Empirically check the survey's qualitative claim that OMT, MILP and CP are
*complementary* paradigms, along three axes:

1. **Pure-linear problems** — does mathematical programming dominate?
2. **Disjunction-dense problems** — does OMT's native boolean handling beat
   MILP's big-M linearization?
3. **Bit-vector problems** — does OMT model what MILP/CP cannot naturally?

## Single source of truth → four equivalent encodings

Each instance is one structured `spec` (a plain dict, deterministic in
`(family, size, seed)`). From it we derive:

* **OMT** — SMT-LIB2 with one `__obj` variable and `(minimize|maximize __obj)`,
  plus `:produce-models true` (OptiMathSAT requires it). Parsed uniformly from
  the `(__obj <value>)` line.
* **MILP (linear families)** — a direct PuLP model (standard LP, no disjunction).
* **MILP (disjunctive family)** — the job-shop no-overlap is a genuine
  disjunction, encoded with **Pyomo.GDP** and reformulated by recognized
  transformations: `gdp.bigm` (textbook big-M) and `gdp.hull` (convex hull). We
  deliberately do *not* hand-roll the big-M, for credibility. Commercial solvers
  (Gurobi/CPLEX) instead use their **native indicator constraints**
  (`addGenConstrIndicator` / `add_indicator`). The disjunctive family thus
  doubles as an encoding study: big-M vs. hull vs. indicator.
* **CP (MiniZinc)** — disjunctions written natively with `\/`; solved by Gecode
  / Chuffed.
* **CP (CP-SAT)** — a native OR-Tools model; job-shop uses interval variables +
  `AddNoOverlap` (the idiomatic strong disjunctive formulation).

Because all four describe the *same* optimization problem, a **correctness
cross-check** asserts that every solver proving optimality on an instance
reports the same objective. A mismatch would mean the encodings diverged; the
runner reports it loudly. This is what lets us trust the timing comparison.

## Solver matrix

| Paradigm | Solver       | Interface         | Anytime source            |
|----------|--------------|-------------------|---------------------------|
| OMT      | νZ (Z3)      | SMT-LIB2 CLI      | final only                |
| OMT      | OptiMathSAT  | SMT-LIB2 CLI (`-optimization=TRUE`) | final only |
| MILP     | CBC/HiGHS/SCIP | PuLP direct (linear families) | final only      |
| MILP     | cbc/highs/scip-bigm | Pyomo.GDP big-M (job-shop) | final only        |
| MILP     | highs-hull   | Pyomo.GDP convex hull (job-shop)  | final only        |
| MILP     | gurobi/cplex-ind | native indicator (if licensed) | final only          |
| CP       | Gecode       | MiniZinc CLI      | `--intermediate-solutions`|
| CP       | Chuffed      | MiniZinc CLI (if installed) | `--intermediate-solutions` |
| CP       | CP-SAT       | OR-Tools (native) | solution callback         |

All solvers run **single-threaded** with the same per-instance timeout, for a
fair comparison.

## Metrics

* **status** — proved-optimal / feasible / unsat / timeout / error. The
  solved/total tables and cross-check use *proved-optimal* only.
* **runtime_s** — wall-clock.
* **memory_peak_mb** — peak RSS of the process tree, polled at 50 ms. Exact for
  subprocess solvers (Z3, OptiMathSAT, CBC, MiniZinc); for in-process backends
  (HiGHS, SCIP, CP-SAT) it includes the Python interpreter baseline, so treat it
  as an upper-bound proxy, not a micro-benchmark.
* **anytime** — `(t, incumbent)` trajectory + best-at-10/30/60 s. Native for
  CP-SAT and MiniZinc; OMT/MILP fall back to the coarse "known from total
  runtime onward" rule.

## Reproducibility & resume

`results.jsonl` is appended one line per `(instance, solver)` and flushed
immediately, so a crashed long run loses nothing. `run_all.py --resume` skips
pairs already present. `gen_benchmarks.py` regenerates byte-identical encodings
from the manifest, so only the (small) manifest + results need to be committed.

## Threats to validity

* **Benchmark representativeness** — families are parametric, derived from real
  application encodings but not drawn from an industrial instance library.
* **Configuration** — single-thread, default parameters, fixed timeout; results
  do not extrapolate to tuned/parallel/long runs.
* **Metric** — we time *proving optimality*, not first-feasible quality; the
  anytime trajectory partially addresses this for CP solvers.
* **Memory** — approximate for in-process backends (see above).
