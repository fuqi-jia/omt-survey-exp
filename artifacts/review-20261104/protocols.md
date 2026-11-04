# Operational definitions

## CGM selection, objectives and engines

The original archive is
`http://www.cgm-tool.eu/download/Experiment_SMT_Files.zip`, SHA-256
`d780f44fbaf3f73e5a307d6b74bb37fa1fe2c2896842981ecb3df55c55acf281`.
Its nested `exp2.zip` has selected members
`exp2/2N{p}P/Experiment_{N}/{i}.smt2`, with N in {2,11,21}, p in {6,8,12}.
The released p=8 groups have i=1..200; p=6,12 have i=1..100.
The sole excluded file, `exp2/2N12P/Experiment_2/100.smt2`, contains only
option commands and no declarations, hard constraints or soft objectives.
Its actual bytes and hash are retained under `excluded_inputs` and in the
server manifest. The other 1199 inputs are all included.

The three lexicographic objectives, in order, are `unsat_preferences`,
`unsat_requirements`, and `sat_tasks`. Positive-weight soft groups encode
these costs. Other, signed auxiliary groups define numeric attributes used
by hard constraints. `scripts/maxsmt_public_20261103.py:encode` preserves
all native OptiMathSAT PB commands in their original order; for Z3 it expands
only non-objective groups as exact ITE sums, preventing extra implicit soft
objectives. Original sources, converted inputs, objective group sizes and
hashes are archived.

Z3 calls use `opt.priority=lex` and `opt.maxsat_engine=maxres` or `wmax`.
OptiMathSAT calls use `-optimization=TRUE -opt.priority=lex`, plus
`-opt.maxsmt_engine=omt -unsat_core_generation=0` or
`-opt.maxsmt_engine=maxres -unsat_core_generation=1`. Exact commands are in
each result record. The server wrapper records CPU affinity, single-core
calls, 4 GiB address-space limits and 600-second process budgets. A saved
returned model is checked against original hard constraints and all three
costs are recomputed. A completed optimal call or a hard-UNSAT call counts
as completed; timeouts do not. The breakdown separates them: each engine
has 41 hard-UNSAT results, and optimal counts are 1158, 916, 996 and 1089
for Z3-MaxRes, Z3-WMax, OMS-OMT and OMS-MaxRes respectively.

## FP timing, cutoff and verification

The snapshot is `runs/public_fp_full_20261030/runner.py`; the maintained
copy is `scripts/public_fp_full_20261030.py`. All 1120 original FP inputs
are used. Each child process is pinned to one CPU and has a 4 GiB address
space limit.

- Native OptiMathSAT: the complete CLI process has a 30-second wall budget.
- Derived Z3 routes: preparation is a separate process with a 35-second wall
  budget. It loads the original FP formula and constructs the FP+BV input;
  the BV route also applies `simplify`, `fpa2bv`, `simplify`.
- Z3 optimization: `Optimize.check()` uses an internal 30000 ms timeout;
  its recorded `elapsed_s` surrounds the check. Process startup, imports
  and input loading precede that timer. The containing process has a
  35-second wall budget covering startup/loading/check/output. Thus the
  five seconds are process overhead allowance, not exclusively cleanup.
  Preparation time is separate from query time; these are not a common
  end-to-end 30-second budget across routes.
- A derived candidate is extracted only for a successful result with equal
  objective bounds and a matching model key. Unknown, process timeout or
  memory failure does not count as completion.
- A separate verifier loads the **original FP constraints**. It issues an
  attainability query and a strict-improvement query, each with a 30000 ms
  timeout; the containing process has a 65-second limit. Completion requires
  attainability SAT and strict improvement UNSAT. Unknown/timeout/OOM maps
  to `unverified_candidate` and is excluded.
- Native verification uses the returned FP literal, logical equality for
  attainability and FP LT/GT for strict improvement. Derived verification
  uses the declared unsigned BV key order and excludes NaN. This order
  refines signed zero as -0 < +0. The verifier does not silently substitute
  native FP comparison for the BV objective order.

`fp/budget-audit.json` and the per-result CSV audit every counted record:
568, 622 and 288 completions, with no counted optimization or verification query time above
30 seconds. Original wall/query times and all verification outcomes remain
available in raw logs, including late unknown/timeouts that were excluded.
The separate NaN and zero audit is retained in
`runs/review_diagnostics_20261103/fp/semantics-audit.json`.

## NRA candidate collection and quality

The statistic evaluates the candidate available at the end of a recorded
call or in its archived native solution file. It does not sample the full
incumbent trajectory.

- SMT CLI calls: after normal process exit, parse the returned vector. If a
  finite objective is available without a vector, independently query for
  a witness at that value. A process timeout archives stdout/stderr but
  does not extract an intermediate model from partial output.
- IPOPT/Couenne: load a returned solution vector when the result contains
  one, independently of the termination-condition label. If the native
  call exits abnormally and writes a `.sol`, recovery is allowed only
  after byte-identical NL reconstruction verifies the column mapping.
  Original error records remain in `solver-run.json`; vectors are not
  repaired. `solution-file-recovery.json` identifies these cases.
- SLSQP: evaluate the final `result.x` even if its convergence flag is false.
  A callback timeout does not retain a partial trajectory.
- Gurobi: extract the final incumbent if `SolCount > 0`, including a time
  limit with an incumbent; preserve native solver status separately.

All extracted vectors face the same variable-bound/constraint check:
maximum violation scaled by `max(1,abs(bound))` <= 1e-6. A feasible vector
hits the reference when `abs(f-f_ref)/max(1,abs(f_ref)) <= 1e-6`. Public
MINLPLib references are PRIMALBOUND values from best-known feasible points;
analytic cases retain their explicit exact references. Candidate quality
and native optimality status are distinct recorded fields. The CSV separates
reference hits, worse feasible points, infeasible vectors and no candidate.

## Diagnostic state preservation

`case-index.json` retains native status, adapter interpretation and paper
classification as separate fields. A CLI `sat` token is not silently
promoted to an independently checked optimality certificate. OptiMathSAT
API statuses and objective fields are captured directly. Couenne native
`.sol` files, logs and Pyomo termination labels remain together. Gurobi's
Hilbert run has status 2 (`OPTIMAL`); the exact rational residual is 1/10.
The two 2^40 diagnostics retain native settings/logs and compare original
coefficients against an order-equivalent `85*k+d` objective. These records
establish the observed outcomes, without assigning an untested internal
cause to scaling, presolve or numeric arithmetic.
