# exact-SCIP (SCIP exact rational MIP) — build note

The pip/conda SCIP (pyscipopt) is compiled **without** exact-solve support. To run
the exactness experiment's `scip-exact` solver, build SCIP from source with the
exact rational mode enabled (needs GMP + MPFR + Boost + an exact SoPlex).

The resulting binary `tools/scip-exact/scip` is **gitignored** (regenerable); only
this note is tracked. `scripts/exact_experiment.py` finds it via `$SCIP_EXACT` or
`tools/scip-exact/scip`.

## Build (Linux/WSL, ~10 min)

```bash
# deps: gmp, mpfr, boost, cmake, gcc (all standard apt packages)
git clone --depth 1 https://github.com/scipopt/soplex.git
git clone --depth 1 https://github.com/scipopt/scip.git

# 1. SoPlex with GMP+Boost (provides the exact/rational LP)
cmake -S soplex -B soplex/build -DCMAKE_BUILD_TYPE=Release -DGMP=ON -DBOOST=ON
cmake --build soplex/build -j

# 2. SCIP with EXACTSOLVE=ON, using that SoPlex
cmake -S scip -B scip/build -DCMAKE_BUILD_TYPE=Release \
      -DEXACTSOLVE=ON -DLPS=spx -DSOPLEX_DIR=$PWD/soplex/build \
      -DGMP=ON -DMPFR=ON -DBOOST=ON \
      -DZIMPL=off -DIPOPT=off -DPAPILO=off -DSYM=none -DREADLINE=off
cmake --build scip/build -j --target scip

cp scip/build/bin/scip tools/scip-exact/scip   # version used: SCIP 11.0.0 / SoPlex 9.0.0
```

## Usage / how the experiment uses it

Exact mode is enabled with `set exact enable TRUE`; coefficients are written as
exact integers in an LP file (SCIP's exact reader stores them as rationals —
verified by round-tripping `write problem`). Classification uses SCIP's reported
`Exact Primal Bound` vs the brute-force optimum.

## Findings (exactness benchmark, coeff = 2^e + offset, 10 instances/cell)

| magnitude | scip-exact | float MILP | int64 CP-SAT | OMT |
|---|---|---|---|---|
| 2^40  | 10/10 exact | ~exact (SCIP scaling fails) | 10/10 | 10/10 |
| 2^54  | **10/10 exact** | wrong (2–4/10) | 10/10 | 10/10 |
| 2^60  | **10/10 exact** | wrong | refuse (int64) | 10/10 |
| 2^200 | refuse* | wrong | refuse | **10/10** |

\* At 2^200 the coefficient exceeds SCIP's finite-value bound (`numerics/infinity`
≈ 1e20, not raisable past the cap), so SCIP **refuses to read** the model
("objective value is infinite") — a *safe refusal*, never a wrong answer.

**Takeaway:** exactness is a property of the *arithmetic*, not the MILP paradigm —
exact-rational MILP (exact-SCIP) is exact wherever default float MILP fails, up to
SCIP's ~1e20 magnitude cap. OMT's arbitrary-precision rational has no such cap, so
it alone stays exact at 2^200.
