# Job-shop cumulative call times

The figure answers how the total observed solving cost changes with job count across the configurations in the manuscript scheduling table. It is a descriptive comparison of archived calls, with no new solver runs or statistical intervals.

- Source: `runs/paper_refresh_20261030/results.csv` (SHA-256 in `provenance.json`).
- Included: all 11 scheduling-table configurations, four job counts (7–10), ten generated instances per count: 440 calls.
- Selection: the separate HiGHS convex-hull configuration has 40 additional records and is outside the scheduling-table columns; it is not mixed into the big-M series.
- Metric: the sum of recorded `runtime_s` for all ten calls at each size, including calls that did not prove optimality. The x marker identifies such a size; it is not a runtime estimate.
- Data: `source-data.csv` retains the individual observations; `plot-data.csv` contains the 44 plotted totals and completion counts.
- Panel roles: OMT implementations, open-source MILP baselines, commercial MILP/encoding alternatives, and CP baselines. All panels use the same axes and metric.
- Export: Python/matplotlib; editable PDF/SVG and a 600-dpi PNG preview, 155.15 × 88 mm to match the manuscript text width.

## Reproduce

```bash
python scripts/plot_jobshop_cumulative_20261106.py
```

The script uses matplotlib, the manuscript's Windows fonts, and the installed nature-figure alignment auditor. `--font-dir` and `--qa-scripts` can select equivalent local installations.

## Rendered QA

Alignment passed the 1.5-point tolerance. The final PDF passed the glyph-size audit (minimum 7 points) and collision audit (zero failures or warnings). Every panel was visually inspected after export.

Three static-preflight warnings are documented: the width follows this manuscript rather than the 89/183-mm Nature defaults; PDF is the submission line-art asset and PNG is its preview, so a TIFF is unnecessary; the positivity check is in the data loader, where every runtime is asserted finite and strictly positive before logarithmic plotting. No resampling, confidence bands or inferred missing values are used.
