#!/usr/bin/env python3
"""Check completeness and provenance of every refreshed manuscript experiment."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'runs'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts/summarize_refresh_20261028.py'),
                    '--require-complete'], check=True)
    performance = RUNS / 'paper_refresh_20261028'
    summary = read(performance / 'summary.json')
    assert summary['instances_with_proofs'] == 97
    for instance in read(performance / 'manifest.json')['instances']:
        for item in instance['inputs'].values():
            assert digest(performance / item['path']) == item['sha256']
    memory_failures = []
    external_timeouts = []
    for row in read(performance / 'results.json'):
        assert row['status'] in {'OPTIMAL', 'SAT', 'TIMEOUT', 'ERROR'}, row
        assert not row.get('proved_optimal') or row['status'] == 'OPTIMAL', row
        if row['status'] == 'ERROR':
            message = str(row.get('error_message', '')).lower()
            assert 'memory' in message or 'bad_alloc' in message, row
            memory_failures.append([row['name'], row['solver']])
        if row.get('external_timeout_s'):
            assert row['status'] == 'TIMEOUT' and row['returncode'] == -9
            assert row['runtime_s'] >= row['external_timeout_s'] == 630
            original = read(performance / 'classification-originals' /
                            (row['name'] + '__' + row['solver'] + '.json'))
            assert original['runtime_s'] == row['runtime_s']
            assert original['status'] == 'ERROR' and not original['proved_optimal']
            external_timeouts.append([row['name'], row['solver']])

    exact = {}
    for name in ['results-open.json', 'results-commercial.json']:
        rows = read(RUNS / 'exact_refresh_20261028' / name)
        assert len(rows) == 40
        for row in rows:
            key = (row['exp'], row['n'], row['seed'])
            case = exact.setdefault(key, {'true_opt': row['true_opt'], 'solvers': {}})
            assert case['true_opt'] == row['true_opt']
            assert not case['solvers'].keys() & row['solvers'].keys()
            case['solvers'].update(row['solvers'])
    expected = {'z3', 'optimathsat', 'cpsat', 'cbc', 'highs', 'scip',
                'scip-exact', 'gurobi', 'cplex'}
    rates = {s: {str(e): 0 for e in [40, 54, 60, 200]} for s in sorted(expected)}
    assert len(exact) == 40
    for (exponent, size, seed), row in exact.items():
        assert size in {8, 12} and 0 <= seed < 5 and set(row['solvers']) == expected
        for solver, result in row['solvers'].items():
            if result['status'] == 'exact':
                assert result['value'] == row['true_opt']
                assert result.get('feasible', True)
                rates[solver][str(exponent)] += 1

    hilbert = {}
    for name in ['results-open.json', 'results-commercial.json']:
        for row in read(RUNS / 'illcond_refresh_20261028' / name):
            assert row['solver'] not in hilbert
            assert set(row['by_n']) == {'6', '8', '10', '12', '14', '16'}
            hilbert[row['solver']] = row['by_n']
    assert set(hilbert) == {'z3', 'optimathsat', 'cbc', 'highs', 'scip', 'gurobi', 'cplex'}

    nra = RUNS / 'nra_20261028'
    rows = read(nra / 'results.json')
    assert len(rows) == 18 and len({(r['case'], r['solver']) for r in rows}) == 18
    assert collections.Counter(r['solver'] for r in rows) == {'z3': 6, 'ocac': 6, 'optimathsat': 6}
    for row in rows:
        source = nra / row['solver'] / (row['case'] + '.smt2')
        assert digest(source) == row['input_sha256']
    scipy = read(nra / 'scipy.json')
    gurobi = read(nra / 'gurobi.json')
    assert scipy['version'] == '1.18.1' and len(scipy['records']) == 8
    assert gurobi['version'] == [13, 0, 3] and len(gurobi['records']) == 6

    fp = RUNS / 'public_fp_full_20261028'
    records = [read(p) for p in sorted((fp / 'cases').glob('*.json'))]
    assert len(records) == 1120 and {r['index'] for r in records} == set(range(1120))
    counts = {s: collections.Counter() for s in ['fp', 'bvfp', 'bv']}
    groups = {}
    statuses = {'verified', 'unverified_candidate', 'timeout', 'out_of_memory', 'unsat', 'nan'}
    for row in records:
        assert set(row['routes']) == set(counts)
        group = groups.setdefault(row['group'], dict(instances=0, fp=0, bvfp=0, bv=0))
        group['instances'] += 1
        for route, result in row['routes'].items():
            assert result['status'] in statuses
            counts[route][result['status']] += 1
            if result['status'] == 'verified':
                verification = result['verification']
                assert verification['attainable'] == 'sat'
                assert verification['strictly_better'] == 'unsat'
                group[route] += 1
    fp_summary = read(fp / 'summary.json')
    assert groups == fp_summary['groups']
    assert counts == fp_summary['route_status_counts']
    delivery = read(fp / 'delivery.json')
    assert digest(fp / 'raw-logs.tar.gz') == delivery['raw_logs_sha256']
    assert digest(fp / 'runner.py') == delivery['runner_sha256']
    assert digest(ROOT / 'scripts/public_fp_full.py') == delivery['runner_sha256']

    report = dict(performance_calls=993, performance_instances=97,
                  objective_mismatches=summary['objective_mismatches'],
                  memory_failures=memory_failures, exact_rates=rates,
                  external_timeouts=external_timeouts,
                  hilbert=hilbert, nra_calls=32,
                  public_fp_instances=1120, public_fp_calls=3360,
                  public_fp_statuses=counts)
    (RUNS / 'toolchain_20261028' / 'delivery-audit.json').write_text(
        json.dumps(report, indent=2))
    print('PASS: all refreshed manuscript experiments are complete and internally consistent.')


if __name__ == '__main__':
    main()
