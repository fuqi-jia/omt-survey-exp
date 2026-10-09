#!/usr/bin/env python3
"""Summarize complete observations, retaining every source and outcome category."""
import collections
import csv
import gzip
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
SUITES = ['fp', 'bv', 'bv_lia', 'maxsmt']


def group(suite, path):
    parts = Path(path).parts
    if suite == 'fp':
        return parts[parts.index('fp') + 2]
    if suite == 'maxsmt':
        return parts[-3] + '/' + parts[-2]
    return parts[-3]


def number(value):
    return value if math.isfinite(value) else None


def statistics_for(rows):
    statuses = collections.Counter(r['status'] for r in rows)
    verified = sum(r['verification'] == 'verified_optimal' for r in rows)
    proven = [r for r in rows if r['status'] == 'solver_claimed_optimal']
    definitive_states = {'solver_claimed_optimal', 'infeasible'}
    definitive = [r for r in rows if r['status'] in definitive_states]
    times = [float(r['wall_s']) for r in definitive]
    # Do not disguise invalid source files as optimization failures or successes.
    # Both denominators are explicit and all rows stay in the source count.
    valid = [r for r in rows if r['status'] != 'invalid_input']
    ranked = [float(r['wall_s']) if r['status'] in definitive_states else math.inf for r in valid]
    return dict(source_inputs=len(rows), valid_inputs=len(valid), outcomes=dict(statuses),
                reported_outcomes=dict(collections.Counter(r.get('reported_status') or r['status'] for r in rows)),
                reviewed_native_failures=sum(bool(r.get('status_review')) for r in rows),
                independently_verified=verified, claimed_optimal=len(proven),
                claimed_definitive=len(definitive),
                verified_after_claim=sum(r['verification'] == 'verified_optimal' for r in proven),
                median_with_unsolved_infinity=number(statistics.median(ranked)) if ranked else None,
                solved_median_s=statistics.median(times) if times else None,
                solved_min_s=min(times) if times else None,
                solved_max_s=max(times) if times else None,
                par2_s=sum(float(r['wall_s']) if r['status'] in definitive_states else 1200
                           for r in valid)/len(valid) if valid else None)


def main():
    progress = json.loads((OUT / 'coverage-progress.json').read_text())
    evidence = {r['suite']: r for r in progress['experiments']}
    assert set(evidence) == set(SUITES), 'Not all four suites have been submitted'
    assert all(r['all_inputs_completed'] for r in evidence.values()), 'Incomplete coverage or unresolved errors'
    summaries = {}
    for suite in SUITES:
        path = OUT / (suite + '-results.csv')
        with path.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == evidence[suite]['expected_solver_runs']
        cells = collections.defaultdict(list)
        by_variant = collections.defaultdict(list)
        for row in rows:
            cells[(group(suite, row['path']), row['variant'])].append(row)
            by_variant[row['variant']].append(row)
        summaries[suite] = dict(
            diagnostic_only=suite=='bv_lia',
            planned_inputs=evidence[suite]['planned_inputs'], solver_runs=len(rows),
            overall={v: statistics_for(rs) for v, rs in sorted(by_variant.items())},
            by_group=[dict(group=g, variant=v, **statistics_for(rs)) for (g, v), rs in sorted(cells.items())],
            by_host=dict(collections.Counter(r['host'] for r in rows)))
        if suite=='bv_lia':
            for stats in list(summaries[suite]['overall'].values()) + summaries[suite]['by_group']:
                for field in ['par2_s','median_with_unsolved_infinity','solved_median_s','solved_min_s','solved_max_s']:
                    stats.pop(field,None)
            summaries[suite]['scope']='Original lexicographic LIA companions; no bit-domain bounds inferred; raw status/bounds diagnostics only'
        # A portable compact copy retains every row; the readable CSV remains
        # beside it on disk. Gzip timestamps are fixed for reproducible bytes.
        with (OUT / (suite + '-results.csv.gz')).open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as packed:
                packed.write(path.read_bytes())
    report = dict(source_snapshot_utc=progress['observed_utc'], budget_s=600,
                  timing='Per-solver wall time including normalization, parsing and startup; verification excluded',
                  par2='Valid inputs only; 2 x 600 seconds unless the solver claims optimal or infeasible',
                  unverified_claims='Reported separately; not called independently established optima',
                  status_reviews='Exact native std::bad_alloc responses are counted as allocation failures; original platform metrics and reported statuses remain preserved and reviews are verified against raw archives.',
                  suites=summaries)
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
