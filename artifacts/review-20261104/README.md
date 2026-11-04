# OMT survey experiment materials — 2026-11-04

This is the fixed material entry for the survey's Tables 6–14. The release
`jos-review-20261104` pins a repository commit; the release archive and its
SHA-256 provide an additional downloadable snapshot. Solver binaries and
commercial licences are not included. Versions and original command lines
are retained in the cohort records.

## Read a result

| Paper result | Authoritative cohort | Audit / file mapping |
|---|---|---|
| Tables 6–8: linear integer and scheduling | `runs/paper_refresh_20261030/` | `REPRODUCE_20261030.md`, cell records and raw output |
| Table 9: CGM MaxSMT | `runs/maxsmt_cgm_server_20261103/` | `runs/review_diagnostics_20261104/cgm/results.csv`, `breakdown.csv` |
| Table 10: large coefficients | `runs/exact_refresh_20261030/` | exact enumeration, original command/output; targeted cases below |
| Table 11: Hilbert systems | `runs/illcond_refresh_20261030/` | original rational specification; n=10 diagnostic below |
| Table 12: one-variable NRA | `runs/nra_20261030/`, `runs/nra_numeric_extensions_20261102/` | six original formulas, native outputs and numerical counterparts |
| Table 13(a): nonlinear candidates | `runs/nra_public_20261102/`, `runs/nra_disjunctive_20261102/` | `runs/review_diagnostics_20261104/nra/candidates.csv`, `breakdown.csv` |
| Table 13(b): irrational nonconvex cases | `runs/nra_irrational_20261102/` | model JSON, SMT/NL inputs, original logs and analytic references |
| Table 14: complete public FP suite | `runs/public_fp_full_20261030/` | `runs/review_diagnostics_20261104/fp/results.csv`, `budget-audit.json` |

The CGM server cohort is the source of Table 9. Earlier local CGM runs have
different timings and are not substituted into that table. The Oct 30 exact,
Hilbert and one-variable NRA cohorts reuse unchanged non-Z3 calls from Oct 29;
their provenance records retain that fact. No historical run is relabelled.

## Diagnostic evidence chains

[`case-index.json`](case-index.json) maps each diagnostic to its actual input,
driver, invocation, raw output, native state, adapter state and final paper
classification. Every indexed file has a SHA-256. It includes:

- OptiMathSAT's strict NRA instance and A_5;
- Couenne's unbounded example and C_(29,5), including the original `.sol`;
- Gurobi's Hilbert n=10 output and exact residual;
- one SCIP and one HiGHS 2^40 case, both original and equivalent small-coefficient encodings.

**Correction preserved in the record.** The Nov 3 API diagnostic for the
strict example rebuilt `x*x >= 2`, whereas the actual CLI input has `x*x > 2`.
The Nov 4 driver rebuilds the strict inequality exactly and supersedes that
API diagnostic. It still reports `SAT_OPTIMAL` with `MSAT_OPTIMUM=1+epsilon`;
the returned model is x=2. The paper's anomaly concerns the reported bound,
not failure of a feasible model to attain an unattained infimum. Old records
are retained for provenance.

## Inputs and checks

The 97 structured performance models and their 194 byte-matched SMT/MiniZinc
inputs are in `benchmarks/performance-20261030/inputs.tar.gz`. The JSON
specifications are also the inputs consumed by the MILP/CP-SAT API adapters.

The release includes all 1199 CGM originals and their 4796 exact solver inputs
in `benchmarks/maxsmt-cgm-20261103/inputs.tar.gz`. Their individual hashes match
the server result records. To restore the directory layout expected by the
original drivers:

```bash
tar -xzf benchmarks/performance-20261030/inputs.tar.gz -C runs/paper_refresh_20261030
mkdir -p runs/maxsmt_cgm_server_20261103/inputs
tar -xzf benchmarks/maxsmt-cgm-20261103/inputs.tar.gz -C runs/maxsmt_cgm_server_20261103/inputs
tar -xzf benchmarks/public_fp/original-fp-inputs-20261104.tar.gz -C benchmarks/public_fp
```

The FP archive contains all 1120 original FP inputs. Raw solver and verification
logs are in `runs/public_fp_full_20261030/raw-logs.tar.gz`; each CSV row gives
its member prefix. The original public source locations and selection hashes
are preserved in benchmark manifests.

```bash
python3 scripts/check_review_artifact_20261104.py
python3 scripts/audit_review_20261104.py
```

The first command uses only the standard library and checks evidence hashes,
counts and the exact diagnostic arithmetic. The second recomputes the full
CGM/FP/NRA classifications and requires the recorded scientific Python
dependencies. Re-running solver calls requires the versions, paths and
commercial licences documented by `REPRODUCE_20261030.md`,
`REPRODUCE_20261102.md` and `REPRODUCE_MAXSMT_20261103.md`.

Detailed timing and candidate-collection definitions are in
[`protocols.md`](protocols.md). A manifest hash verifies archived evidence;
it does not itself prove a solver's optimality claim.
