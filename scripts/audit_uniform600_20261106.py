#!/usr/bin/env python3
"""Audit all fresh local numerical/NRA records and write the table data."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from uniform600_20261106 import ROOT, OUT, configure, save


def numerical():
    exact = {}
    for path in sorted((OUT / 'exact').glob('*/results-*.json')):
        rows = json.loads(path.read_text())
        assert len(rows) == 40, path
        solver = path.parent.name
        by_exp = {str(e): Counter() for e in [40, 54, 60, 200]}
        for row in rows:
            assert set(row['solvers']) == {solver}
            result = row['solvers'][solver]
            by_exp[str(row['exp'])][result['status']] += 1
            if result['status'] == 'exact':
                assert result['value'] == row['true_opt']
            raw = path.parent / 'raw' / f"{row['exp']}_{row['n']}_{row['seed']}__{solver}.process.json"
            assert json.loads(raw.read_text())['returncode'] == 0
        exact[solver] = {e: dict(c) for e, c in by_exp.items()}
    assert len(exact) == 9
    illcond = {}
    for path in sorted((OUT / 'illcond').glob('*/results-*.json')):
        rows = json.loads(path.read_text())
        assert len(rows) == 1 and len(rows[0]['by_n']) == 6
        row = rows[0]
        illcond[row['solver']] = row['by_n']
        for n in row['by_n']:
            raw = path.parent / 'raw' / f"{n}__{row['solver']}.process.json"
            assert json.loads(raw.read_text())['returncode'] == 0
    assert len(illcond) == 7
    for path in list((OUT / 'exact').glob('*/environment-*.json')) + list((OUT / 'illcond').glob('*/environment-*.json')):
        assert json.loads(path.read_text())['timeout_s'] == 600
    for item in json.loads((OUT / 'instance_manifest.json').read_text()):
        assert hashlib.sha256((OUT / item['path']).read_bytes()).hexdigest() == item['sha256']
    save(OUT / 'numerical-audit.json', dict(passed=True, exact_calls=360, hilbert_calls=42,
         exact=exact, illcond=illcond, inputs=46, timeout_s=600, execution='local'))
    return dict(exact_calls=360, hilbert_calls=42, passed=True)


def nonlinear(partial=False):
    import nra_public_20261102 as public
    import nra_disjunctive_20261102 as disj
    import nra_irrational_20261102 as irr
    missing, records, counts = [], [], {}
    for label, module, solvers in [
        ('public', public, ['z3', 'ocac', 'optimathsat', 'scipy', 'ipopt', 'couenne', 'gurobi']),
        ('disjunctive', disj, ['z3', 'ocac', 'optimathsat', 'couenne', 'gurobi']),
        ('irrational', irr, ['z3', 'ocac', 'optimathsat', 'couenne', 'gurobi'])]:
        for model_path in sorted((module.OUT / 'models').glob('*.json')):
            model = json.loads(model_path.read_text())
            labels = solvers + (['scipy_I', 'scipy_II', 'ipopt_I', 'ipopt_II']
                                if label == 'irrational' and model['family'] != 'C' else [])
            for solver in labels:
                path = module.OUT / solver / model['name'] / 'result.json'
                if not path.exists():
                    missing.append(str(path.relative_to(OUT)))
                    continue
                result = json.loads(path.read_text())
                assert result['timeout_s'] == 600, path
                assert result['model_sha256'] == hashlib.sha256(model_path.read_bytes()).hexdigest(), path
                assessed = module.assess(model, result.get('x'), model['reference'])
                assert assessed['feasible'] == result['feasible'], path
                assert assessed['reference_hit'] == result['reference_hit'], path
                records.append(result)
        cohort_records = [json.loads(p.read_text()) for p in module.OUT.glob('*/*/result.json')]
        counts[label] = dict(Counter(r['solver'] for r in cohort_records))
    simple = OUT / 'nra_base'
    for solver in ['z3', 'ocac', 'optimathsat']:
        import nra_refresh_20261028 as base
        for case in base.CASES:
            path = simple / solver / (case[0] + '.json')
            if not path.exists():
                missing.append(str(path.relative_to(OUT)))
                continue
            result = json.loads(path.read_text())
            assert result['timeout_s'] == 600
            source = path.with_suffix('.smt2')
            assert result['input_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    for solver, expected in [('scipy', 8), ('gurobi', 6)]:
        path = simple / (solver + '.json')
        if not path.exists():
            missing.append(str(path.relative_to(OUT)))
        else:
            assert len(json.loads(path.read_text())['records']) == expected
    for solver, expected in [('ipopt', 8), ('couenne', 6)]:
        path = OUT / 'nra_extensions' / (solver + '.json')
        if not path.exists():
            missing.append(str(path.relative_to(OUT)))
        else:
            results = json.loads(path.read_text())['records']
            assert len(results) == expected
            assert all(r['timeout_s'] == 600 for r in results)
    report = dict(passed=not missing, completed_matrix_calls=len(records), missing=missing, cohorts=counts)
    save(OUT / 'nonlinear-progress.json', report)
    if not partial:
        assert not missing, missing
        assert len(records) == 415
        report['total_nonlinear_calls'] = 461
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    configure()
    a = numerical()
    b = nonlinear(args.partial)
    print(json.dumps(dict(numerical=a, nonlinear_completed=b['completed_matrix_calls'],
                         nonlinear_missing=len(b['missing']), cohorts=b['cohorts']), indent=2))
    if not args.partial:
        save(OUT / 'delivery-audit.json', dict(passed=True, numerical=a, nonlinear=b,
             total_new_calls=863, timeout_s=600, execution='local Intel Core i7-11700F'))


if __name__ == '__main__':
    main()
