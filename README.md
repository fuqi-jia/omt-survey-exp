# OMT Survey — Experiments

A reproducible **three-paradigm comparison** — Optimization Modulo Theories
(OMT) vs. Mixed-Integer Linear Programming (MILP) vs. Constraint Programming
(CP) — backing the experiment section of the OMT survey.

Every benchmark instance is described by **one structured spec** from which we
emit **four provably-equivalent encodings**. A correctness cross-check confirms
that all solvers proving optimality on an instance agree on the objective, so
the timing comparison is built on genuinely equivalent problems.

Instance generation is deterministic: `build(family, size, seed)` reproduces a
byte-identical instance, which is what lets separate runs (Linux/Windows,
main harness/side experiments) be merged or compared cell by cell.

## Where to look

| You want | Read |
|---|---|
| What is here, how to run it | this file |
| Where each published number came from, plus every caveat and known defect | **`DATA_PROVENANCE.md`** (Chinese) |
| Camera-ready results: table bodies, claims to correct, quotable wording | **`RESULTS_FOR_PAPER.md`** (Chinese) |
| Harness design notes | `docs/design.md` |

## Paradigms and solvers

| Paradigm | Solvers (auto-detected)            | Encoding             |
|----------|------------------------------------|----------------------|
| OMT      | νZ (Z3), OptiMathSAT               | SMT-LIB2 (`smt2/`)   |
| MILP     | CBC, HiGHS, SCIP                    | PuLP direct (linear families) |
| MILP     | CBC, HiGHS, SCIP                    | **Pyomo.GDP** big-M / hull (disjunctive family) |
| MILP     | *Gurobi, CPLEX*                    | **native indicator constraints** |
| CP       | Gecode, CP-SAT, *Chuffed*          | MiniZinc (`mzn/`) + native CP-SAT |

*Italic* solvers are optional: used automatically if licensed/installed,
skipped otherwise. So the **same code runs on a laptop and on a server.**

Two more solvers appear only in the side experiments, not in the main matrix:
**CDCL(OCAC)** (a cvc5 fork, complete for OMT(NRA); `tools/cdcl_ocac/cvc5`)
drives the NRA experiment, and **exact SCIP** (built with `EXACTSOLVE=ON` +
GMP/MPFR; `tools/scip-exact/BUILD.md`) drives the exact-arithmetic experiment.

To keep the MILP comparison credible, disjunctions are **not** hand-rolled: the
job-shop big-M (and a convex-`hull` variant) come from the recognized
**Pyomo.GDP** transformations, and Gurobi/CPLEX use their own **native indicator
constraints** rather than a manual big-M. The pure-linear families have no
encoding choice and stay on direct PuLP models. The disjunctive family therefore
doubles as an *encoding study*: big-M vs. hull vs. indicator.

## Benchmark families

Six parametric families derived from the survey's application encodings, each
*feasible by construction* (a well-defined optimum always exists):

| Cat | Family      | Structure                              | Paradigms     |
|-----|-------------|----------------------------------------|---------------|
| A   | `gap`       | Generalized assignment (pure linear)   | OMT/MILP/CP   |
| A   | `knapsack`  | 0-1 multidim. knapsack (pure linear)   | OMT/MILP/CP   |
| B   | `jobshop`   | Job-shop, O(n²) disjunctions           | OMT/MILP/CP   |
| B   | `config`    | System config: deps + mutex            | OMT/MILP/CP   |
| B   | `setcover`  | Weighted set cover (covering)          | OMT/MILP/CP   |
| C   | `bvcover`   | Bit-vector min-cover (bit-level)       | **OMT only**  |

## Quick start

> **Use `.venv-cplex`, not `.venv`.** The root `.venv` resolves `cplex` to the
> pip **Community** edition, which hard-caps at 1000 variables and makes
> `cplex-bigm`/`cplex-ind` bail out with `ERROR` in ~0.004 s on exactly the
> large instances the paper argues about. `.venv-cplex` (Python 3.10 + CPLEX
> Studio 22.1) has no cap. The licence cannot be unlocked on the pip build, so
> the fix is the interpreter, not a flag. See `DATA_PROVENANCE.md` §五 / §7.2.

```bash
# 1. one-time setup: venv + open-source solvers + OptiMathSAT 1.7.4
bash scripts/setup_env.sh

# 2. generate the benchmark suite for a config
.venv-cplex/bin/python scripts/gen_benchmarks.py --config configs/long600.yaml

# 3. run every detected solver (streams to results.jsonl; --resume to continue)
.venv-cplex/bin/python scripts/run_all.py       --config configs/long600.yaml --resume

# 4. build LaTeX tables + figures + summary.md
.venv-cplex/bin/python scripts/analyze.py       --config configs/long600.yaml
```

Outputs land in `runs/<config>/`:
`manifest.json`, `results.csv`, `results.json`, `results.jsonl`, `tables/*.tex`,
`figures/*.png`, `summary.md` (committed); `smt2/ lp/ mzn/` are regenerable and
gitignored.

Always pass `--resume` on the long configs: a run can span half a day, and
`--resume` keys off `results.jsonl`, so an interruption costs only the cell in
flight. Long runs are best started with `nohup`/`setsid` — and probe liveness
with `ps -p <pid>`, **not** file mtime: a 600 s cell writes nothing for ten
minutes and looks dead.

### Full Gurobi is Windows-only here

The full Gurobi licence is **NODE-locked to the Windows host**, so WSL's
`gurobipy` is the size-limited build no matter what. Cells that exceed the free
cap are re-run on Windows and merged back:

```powershell
# on Windows, from the repo root
powershell -File scripts\run_gurobi_windows.ps1        # -> runs/<name>/gurobi_win/
```
```bash
# back in WSL: rebuild the derived CSV/JSON, tagging each row with its source
.venv-cplex/bin/python scripts/merge_gurobi_win.py
```

`scripts/gurobi_long600_windows.py` imports the *same* `experiments` package the
WSL harness uses, so the two sides differ only in licence — not in encoding,
timeout, seed, or instance data. (The older `gurobi_linear_windows.py` hardcodes
30 s / 1 seed / 3 families and must not be used for long-timeout runs.)

## Configs

| Config              | Families × sizes                         | Timeout | Seeds | Purpose |
|---------------------|------------------------------------------|---------|-------|---------|
| `quick.yaml`        | all six, tiny                            | 20 s    | 1     | pipeline smoke |
| `wsl.yaml`          | all six, moderate                        | 60 s    | 3     | local / laptop |
| `full.yaml`         | all six, aggressive                      | 120 s   | 3     | server |
| **`long600.yaml`**  | five separating families (no `bvcover`)  | **600 s** | 3   | **the paper's main run** |
| **`jobshop_seeds.yaml`** | `jobshop` n=7,8,9,10                | **600 s** | **10** | **job-shop seed variance** |
| `sep.yaml` / `sep_large.yaml` / `sep_lin.yaml` | separation study, mid/large/linear | 30 s | 1 | earlier 30 s generation |
| `setcover.yaml`     | `setcover` 48–384                        | 30 s    | 1     | set-cover scaling |
| `jobshop_full.yaml` | `jobshop` 5–10                           | 30 s    | 1     | earlier job-shop pass |
| `enc.yaml`          | `jobshop` 5–8 + `bvcover`                | 30 s    | 1     | encoding study |
| `probe.yaml`        | all six, wide sizes                      | 30 s    | 1     | size calibration |

`long600` is 81 instances × applicable solvers = **801 solves**, ≈12.8 h
wall-clock. `jobshop_seeds` is 40 instances × 12 solvers = **480 solves**, of
which seeds 0–2 are *reused from* `long600` (tagged `"reused_from": "long600"`)
— identical instances by construction, so the medians nest consistently with
already-published data.

## What is measured

Per `(instance, solver)`: status (proved-optimal / feasible / unsat / timeout),
objective, wall-clock time, peak RSS, and an **anytime** incumbent trajectory
(10/30/60 s checkpoints). Anytime curves are captured natively for CP-SAT
(solution callback) and the MiniZinc backends (`--intermediate-solutions`);
OMT/MILP report the final solution (peak RSS is approximate for in-process
backends — it includes the Python interpreter baseline).

Every solve runs single-threaded in its own subprocess under `RLIMIT_AS = 4 GB`,
so one solver's crash or OOM cannot take down the run. Status vocabulary is kept
deliberately fine-grained: a graceful out-of-memory (**MO**) is not a timeout
(**T/O**), and a `worker exit -6` (SIGABRT — HiGHS does this on the hull
encoding) is neither. Conflating them would read as a capability claim.

Medians follow one convention throughout: **a run that did not prove optimality
is ranked `+∞`**, then the median is taken. So `T/O` in a median column means
"unproved in the median sense", and a `k/K` superscript records that only `k`
of `K` seeds proved optimality. `scripts/make_jobshop_table.py` emits the
job-shop table body under exactly this rule.

## Supplementary experiments

Five standalone scripts sit outside the main matrix. Each is self-contained,
deterministic, and writes its own `runs/` directory.

| Script | Output | Question it answers |
|---|---|---|
| `exact_experiment.py` | `runs/exact/` | Does exact arithmetic matter, or is float MILP enough? |
| `illcond_experiment.py` | `runs/illcond/` | Does float MILP fail on *benign, small* coefficients when the system is ill-conditioned? |
| `illcond_experiment.py --objective` | `runs/illcond_obj/` | …and does adding an objective change that? (robustness check) |
| `nra_experiment.py` | `runs/nra/` | On nonlinear reals, who is exact, who is global, who distinguishes the shapes of an optimum? |
| `omt_tuning_probe.py` | `runs/omt_tuning/` | Is the OMT/MILP gap on linear families just a default-parameters artifact? |

### Exact arithmetic

```bash
.venv-cplex/bin/python scripts/exact_experiment.py
```

The raw per-seed artifact is `runs/exact/results.json`. Each record includes
`exp`, `seed`, and `true_opt`, plus a `solvers` object whose per-solver entries
contain `status`, `value`, and (when applicable) `gap_to_opt`; for example,
filtering to `exp == 40` and reading `solvers.scip` locates every SCIP
$2^{40}$ result discussed in the paper. The aggregated counts by solver and
magnitude are in `runs/exact/summary.json`. These committed artifacts, together
with the script, distinguish a solver *status* from whether the returned
assignment is optimal relative to the original exact-integer specification.

The `scip-exact` column is the reason the paper's claim is a four-way
distinction rather than "only OMT is exact": exact SCIP is 10/10 correct at
$2^{40}/2^{54}/2^{60}$ where float MILP has already failed, but *refuses to read*
coefficients past its finite-value ceiling (`numerics/infinity` ≈ 1e20), so
$2^{200}$ is a safe rejection. Only OMT, on unbounded rationals, is exact
throughout.

### Ill-conditioning

```bash
.venv-cplex/bin/python scripts/illcond_experiment.py              # -> runs/illcond/
.venv-cplex/bin/python scripts/illcond_experiment.py --objective  # -> runs/illcond_obj/
```

The instance is the classic Hilbert system `H[i][j] = 1/(i+j+1)`, `b = H·1`,
recovering `x ∈ {0,1,2}^n`. All coefficients lie in (0,1] — nothing large,
nothing planted inside a feasibility tolerance — yet `cond(H) ~ e^{3.5n}` alone
is enough to break float MILP, while rational-arithmetic OMT is unaffected.

`--objective` adds a uniform `min Σᵢ xᵢ` to *every* solver. Since `H` is
invertible the feasible point is unique, so the objective cannot change *which*
solution is returned — any cell that moves is attributable to the search path
alone. **47 of 48 cells are unchanged**; the one that moves is CBC at n=10,
which flips `correct → infeasible`. The paper's table needs no edit; the
finding is a supplement, not a correction. Both directories are kept: the run
that backs the table is never overwritten by a variant.

### NRA optimum shapes

```bash
.venv-cplex/bin/python scripts/nra_experiment.py      # OCAC binary via $OCAC
```

Three instance groups (`runs/nra/results.json`): **A** irrational optimum
(`max x, x²≤k` → `√k`), **B** nonconvex local trap, and **C** the two shapes
where no attained optimum exists — C1 `min x s.t. x>0 ∧ x·x>2` (infimum √2,
**unattained**) and C2 `min x s.t. x·x≥1` (**unbounded below**). C deliberately
carries **no domain bound on `x`**: an artificial lower bound would make both
instances well-behaved and destroy the very thing under test.

> **Reproducer's trap.** On the build under test, the OCAC objective must be
> written as a **compound term**. `(minimize x)` on a bare declared variable
> takes a different front-end path and returns a feasible witness point;
> `(minimize (+ x 0))` — semantically identical — returns the correct
> `√2 + ε` and `-oo`. The script therefore records **both** forms under
> `by_objective_form`, since reporting only one would either hide a real
> invocation trap or wrongly convict a correct algorithm. Two unrelated
> segfaults in the same binary are documented in `DATA_PROVENANCE.md` §9.1.1.

### OMT search-strategy tuning

```bash
.venv-cplex/bin/python scripts/omt_tuning_probe.py             # 600 s, 3 seeds
.venv-cplex/bin/python scripts/omt_tuning_probe.py --timeout 60 --seeds 1
```

Sweeps six configurations — OptiMathSAT `-opt.strategy = lin|bin|ada` plus its
default, and Z3 `opt.optsmt_engine = basic|symba` — over GAP n=160 and weighted
set cover n=240, 3 seeds each: **36 solves**. Two design points keep the
comparison honest:

- Instances are **not regenerated**. The probe consumes the very
  `runs/long600/smt2/*.smt2` files the main run consumed, so it and the table it
  argues about have byte-identical inputs.
- The adapters **subclass the harness's own `Z3Solver`/`OptiMathSATSolver`** and
  override only the command line, so timeout, thread count, and the
  proved-optimal criterion are inherited rather than re-implemented.

Parameter names were verified against the shipped `--help`, not assumed:
`-optimization.search_strategy` does not exist on OptiMathSAT 1.7.4 (writing it
would have silently produced three copies of the default), the real default is
`bin` rather than `lin`, and Z3's `opt.priority` only combines *multiple*
objectives and is inert on a single one.

**Answer: no.** Set cover n=240 times out in all 18 solves; GAP n=160 stays at
the $10^2$ s scale against $0.03$–$0.42$ s for MILP on the same family. Nor can
any single setting be called better — `default(bin)` and explicit `bin` are the
same configuration and still differ by 5% (271.30 vs 257.52 s), which is the
noise floor on this machine. `runs/omt_tuning/summary.txt` has the full grid.

## Which run backs which paper table

| Paper | Run directory | Notes |
|---|---|---|
| `tab:exp-sep` | `runs/long600/` | 600 s, 3 seeds; 6 licence-capped Gurobi cells merged from `runs/long600/gurobi_win/` |
| `tab:exp-jobshop` | `runs/jobshop_seeds/` | 600 s, 10 seeds; body generated by `scripts/make_jobshop_table.py` |
| `tab:exp-exact` | `runs/exact/` | includes `scip-exact` |
| `tab:exp-illcond` | `runs/illcond/` | `runs/illcond_obj/` is the robustness check, not the table |
| `tab:exp-nra` | `runs/nra/` | groups A/B/C |
| §8 tuning paragraph | `runs/omt_tuning/` | the "it's just defaults" rebuttal |

Everything else under `runs/` is the **earlier 30 s generation**
(`sep`, `sep_large`, `sep_lin`, `setcover`, `jobshop_full`, `enc`, `probe`,
`quick`, `wsl`) or a single-purpose licence run (`gurobi_win`, `cplex_lin`).
They are superseded by `long600` but kept: `DATA_PROVENANCE.md` §一 cites them,
and the cross-run agreement is itself part of the evidence.

## Layout

```
experiments/
  __init__.py            SolverResult + stream_run (subprocess + anytime + RSS)
  benchmarks/families.py 6 structured-spec generators (deterministic build())
  encodings/             smt2 / milp(PuLP) / milp_gdp(Pyomo.GDP) / minizinc / cpsat
  solvers/               omt / milp / milp_pyomo / milp_indicator / cp + detect_solvers()
scripts/
  gen_benchmarks.py  run_all.py  analyze.py  setup_env.sh   main pipeline
  make_jobshop_table.py                                     LaTeX table body
  exact_experiment.py  illcond_experiment.py                side experiments
  nra_experiment.py    omt_tuning_probe.py
  gurobi_long600_windows.py  run_gurobi_windows.ps1         full-licence Gurobi
  merge_gurobi_win.py  cplex_linear.py                      merge / full-licence CPLEX
configs/   12 YAML configs (see table above)
tools/     cdcl_ocac/  optimathsat-1.7.4-linux-64-bit/  scip-exact/   (binaries gitignored)
runs/      <config>/                                        (committed artifacts)
```
