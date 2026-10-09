#!/usr/bin/env python3
"""Export one fully completed and archived suite, never a partial sample.

The campaign-wide summary remains gated on all four complete suites. This
checkpoint makes a finished suite reviewable while the other queues continue.
"""
import argparse
import collections
import csv
import datetime
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
from summarize import group, statistics_for

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=['fp', 'bv', 'bv_lia', 'maxsmt'])
    suite = parser.parse_args().suite
    lock = (OUT / 'snapshot.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    progress = json.loads((OUT / 'coverage-progress.json').read_text())
    entries = [r for r in progress['experiments'] if r['suite'] == suite]
    assert len(entries) == 1 and entries[0]['all_inputs_completed'], 'Suite incomplete or has unresolved errors'
    evidence = entries[0]
    manifest_path = ROOT / 'benchmarks/full_public/manifests' / (suite + '.jsonl')
    assert sha(manifest_path) == evidence['manifest_sha256']
    manifest = {r['id']: r for r in map(json.loads, manifest_path.read_text().splitlines())}
    platform = json.loads((OUT / (suite + '-platform.json')).read_text())
    assert platform['experiment']['id'] == evidence['experiment']
    runs = platform['runs']
    assert len(runs) == len(manifest) == evidence['planned_inputs']
    assert all(r['status'] not in {'pending', 'assigned', 'running'} for r in runs)
    hosts = collections.Counter(r['host'] for r in runs)
    archives = json.loads((OUT / (suite + '-archives.json')).read_text())
    assert {r['host']: r['runs'] for r in archives} == dict(hosts), 'Raw archive coverage incomplete'
    assert len({r['host'] for r in archives}) == len(archives)
    for archive in archives:
        path = ROOT / archive['path']
        assert path.stat().st_size == archive['bytes'] and sha(path) == archive['sha256']
    csv_path = OUT / (suite + '-results.csv')
    with csv_path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == evidence['expected_solver_runs']
    assert len({(r['case'], r['variant']) for r in rows}) == len(rows)
    variants = sorted({r['variant'] for r in rows})
    assert {(r['case'], r['variant']) for r in rows} == {(c, v) for c in manifest for v in variants}
    assert all(r['sha256'] == manifest[r['case']]['sha256'] for r in rows)
    cells = collections.defaultdict(list)
    by_variant = collections.defaultdict(list)
    for row in rows:
        cells[(group(suite, row['path']), row['variant'])].append(row)
        by_variant[row['variant']].append(row)
    overall = {v: statistics_for(rs) for v, rs in sorted(by_variant.items())}
    groups = [dict(group=g, variant=v, **statistics_for(rs)) for (g, v), rs in sorted(cells.items())]
    if suite == 'bv_lia':
        for stats in list(overall.values()) + groups:
            for field in ['par2_s', 'median_with_unsolved_infinity', 'solved_median_s', 'solved_min_s', 'solved_max_s']:
                stats.pop(field, None)
    packed = OUT / (suite + '-results.csv.gz')
    with packed.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as target:
            target.write(csv_path.read_bytes())
    report = dict(suite=suite, completed_suite_only=True, campaign_complete=False,
        note='Complete coverage and raw archives for this suite only; other suites retain their independent completion gates.',
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_snapshot_utc=progress['observed_utc'],
        planned_inputs=len(manifest), solver_runs=len(rows), diagnostic_only=suite=='bv_lia',
        manifest_sha256=evidence['manifest_sha256'], coverage=evidence, archives=archives,
        results_csv_sha256=sha(csv_path), results_gzip_sha256=sha(packed),
        budget_s=600, memory_bytes=8 * 1024**3,
        statistics='Reported optimal or infeasible counts as definitive; unsolved valid inputs contribute infinity to the median and 1200 s to PAR-2. Independent verification is reported separately.',
        overall=overall, by_group=groups)
    (OUT / (suite + '-complete.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['suite', 'planned_inputs', 'solver_runs', 'overall']}, indent=2))


if __name__ == '__main__':
    main()
