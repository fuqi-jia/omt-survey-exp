# MINLPLib continuous nonconvex quadratic cohort

Source: [MINLPLib](https://www.minlplib.org/), maintained by Stefan Vigerske.
The archived website snapshot is dated **2026-09-14**, Git `9472b011`.
Original metadata, OSiL models and solution vectors are distributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The original files are retained without coefficient changes.

Selection was fixed before solver runs: continuous, nonconvex instances with
2–5 variables, at most 10 constraints, type QP/QCP/QCQP, reference primal/dual
gap at most `1e-6`, and an OSiL representation. **All 43** qualifying instances
are included. No solver outcome is used in selection. `instancedata.csv` is the
complete public metadata snapshot; `selection.json` records the exact criteria,
selected rows, download URLs and original model hashes.

`reference-points/` contains each instance's best published feasible point;
`sources.json` records its exact download URL. MINLPLib `.sol` files are sparse:
omitted variables have value zero. The shared polynomial reader reproduces all
43 reference objectives and satisfies their constraints at the stated tolerance.
See `runs/nra_public_20261102/reference-encoding-audit.json`.

```bash
python3 scripts/fetch_minlplib_qcqp_20261102.py
```

Reference: M. R. Bussieck, A. S. Drud and A. Meeraus. MINLPLib—A Collection of Test
Models for Mixed-Integer Nonlinear Programming. *INFORMS Journal on Computing*
15(1), 114–119, 2003. [DOI](https://doi.org/10.1287/ijoc.15.1.114.15159).
