# OMT Survey — Experiments

A reproducible **three-paradigm comparison** — Optimization Modulo Theories
(OMT) vs. Mixed-Integer Linear Programming (MILP) vs. Constraint Programming
(CP) — backing the experiment section of the OMT survey.

Every benchmark instance is described by **one structured spec** from which we
emit **four provably-equivalent encodings**. A correctness cross-check confirms
that all solvers proving optimality on an instance agree on the objective, so
the timing comparison is built on genuinely equivalent problems.

| Paradigm | Solvers (auto-detected)            | Encoding             |
|----------|------------------------------------|----------------------|
| OMT      | νZ (Z3), OptiMathSAT               | SMT-LIB2 (`smt2/`)   |
| MILP     | CBC, HiGHS, SCIP, *Gurobi, CPLEX*  | PuLP / big-M (`lp/`) |
| CP       | Gecode, CP-SAT, *Chuffed*          | MiniZinc (`mzn/`) + native CP-SAT |

*Italic* solvers are optional: used automatically if licensed/installed,
skipped otherwise. So the **same code runs on a laptop and on a server.**

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

```bash
# 1. one-time setup: venv + open-source solvers + OptiMathSAT 1.7.4
bash scripts/setup_env.sh

# 2. generate the benchmark suite for a config
.venv/bin/python scripts/gen_benchmarks.py --config configs/wsl.yaml

# 3. run every detected solver (streams to results.jsonl; --resume to continue)
.venv/bin/python scripts/run_all.py       --config configs/wsl.yaml

# 4. build LaTeX tables + figures + summary.md
.venv/bin/python scripts/analyze.py       --config configs/wsl.yaml
```

Outputs land in `runs/<config>/`:
`manifest.json`, `results.csv`, `results.json`, `tables/*.tex`,
`figures/*.png`, `summary.md` (committed); `smt2/ lp/ mzn/` are regenerable and
gitignored.

## Configs

| Config        | Scale         | Timeout | Seeds | Intended for      |
|---------------|---------------|---------|-------|-------------------|
| `quick.yaml`  | tiny          | 20 s    | 1     | pipeline smoke    |
| `wsl.yaml`    | moderate      | 60 s    | 3     | local / laptop    |
| `full.yaml`   | aggressive    | 120 s   | 5     | **server**        |

On a server, run the aggressive config with resume so it survives interruption:

```bash
.venv/bin/python scripts/gen_benchmarks.py --config configs/full.yaml
.venv/bin/python scripts/run_all.py        --config configs/full.yaml --resume
.venv/bin/python scripts/analyze.py        --config configs/full.yaml
```

## What is measured

Per `(instance, solver)`: status (proved-optimal / feasible / unsat / timeout),
objective, wall-clock time, peak RSS, and an **anytime** incumbent trajectory
(10/30/60 s checkpoints). Anytime curves are captured natively for CP-SAT
(solution callback) and the MiniZinc backends (`--intermediate-solutions`);
OMT/MILP report the final solution (peak RSS is approximate for in-process
backends — it includes the Python interpreter baseline).

## Layout

```
experiments/
  __init__.py            SolverResult + stream_run (subprocess + anytime + RSS)
  benchmarks/families.py 6 structured-spec generators
  encodings/             smt2 / milp(PuLP) / minizinc / cpsat(OR-Tools)
  solvers/               omt / milp / cp adapters + detect_solvers()
scripts/
  gen_benchmarks.py  run_all.py  analyze.py  setup_env.sh
configs/   quick.yaml  wsl.yaml  full.yaml
runs/      <config>/  (generated)
```
