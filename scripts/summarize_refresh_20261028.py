#!/usr/bin/env python3
"""Validate the complete manuscript matrix and regenerate numerical table rows."""
import argparse
import collections
import csv
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/paper_refresh_20261028'
LINEAR = ['z3', 'optimathsat', 'cbc', 'highs', 'scip', 'gurobi', 'cplex', 'gecode', 'cpsat']
JOB = ['z3', 'optimathsat', 'cbc-bigm', 'highs-bigm', 'scip-bigm', 'gurobi-bigm',
       'gurobi-ind', 'cplex-bigm', 'cplex-ind', 'gecode', 'cpsat']
FAMILIES = [('gap', 'GAP', [40, 80, 160, 320]),
            ('config', '配置', [40, 80, 150, 200, 300]),
            ('knapsack', '背包', [40, 80, 160, 320, 640]),
            ('setcover', '集合覆盖', [40, 80, 160, 240, 320])]


def quantile(values, p):
    k = (len(values) - 1) * p
    i = int(k)
    return values[i] + (k - i) * (values[min(i + 1, len(values) - 1)] - values[i])


def aggregate(rows, expected):
    ok = sorted(r['runtime_s'] for r in rows if r.get('proved_optimal'))
    values = sorted(r['runtime_s'] if r.get('proved_optimal') else math.inf for r in rows)
    median = statistics.median(values) if len(rows) == expected else math.inf
    memory = sum('memory' in str(r.get('error_message', '')).lower() or
                 'bad_alloc' in str(r.get('error_message', '')).lower() for r in rows)
    return dict(completed=len(rows), expected=expected, optimal=len(ok),
                median=median if math.isfinite(median) else None,
                q1=quantile(ok, .25) if len(ok) == expected else None,
                q3=quantile(ok, .75) if len(ok) == expected else None,
                success_min=min(ok) if ok else None, success_max=max(ok) if ok else None,
                statuses=dict(collections.Counter(r['status'] for r in rows)),
                memory_failures=memory,
                errors=[dict(seed=r['seed'], message=r.get('error_message')) for r in rows
                        if r['status'] == 'ERROR'])


def cell(stat, solver, expected):
    assert stat['completed'] == expected
    if stat['median'] is not None:
        value = '$<$0.01' if stat['median'] < .01 else f"{stat['median']:.2f}"
    elif stat['memory_failures'] > expected / 2:
        value = 'MO'
    elif solver == 'gecode' and stat['statuses'].get('SAT', 0):
        value = 'feas.'
    elif stat['errors'] and stat['memory_failures'] != len(stat['errors']):
        value = 'ERR'
    else:
        value = 'T/O'
    if stat['optimal'] < expected and (stat['optimal'] or expected == 10):
        value += '$^{' + f"{stat['optimal']}/{expected}" + '}$'
    return value


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='runs/paper_refresh_20261028')
    ap.add_argument('--require-complete', action='store_true')
    args = ap.parse_args()
    OUT = ROOT / args.output
    manifest = json.loads((OUT / 'manifest.json').read_text())['instances']
    assert len(manifest) == 97
    expected = {(r['name'], solver) for r in manifest for solver in
                (JOB + ['highs-hull'] if r['family'] == 'jobshop' else LINEAR)}
    assert len(expected) == 993
    rows = []
    for path in sorted((OUT / 'cells').glob('*.json')):
        try:
            rows.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, FileNotFoundError):
            continue  # an active worker may still be writing its record
    found = {(r['name'], r['solver']) for r in rows}
    assert len(found) == len(rows) and found <= expected
    objective = collections.defaultdict(dict)
    by_group = collections.defaultdict(list)
    for r in rows:
        by_group[r['family'], r['size'], r['solver']].append(r)
        if r.get('proved_optimal'):
            objective[r['name']][r['solver']] = r['objective']
    mismatch = {name: values for name, values in objective.items() if len(set(values.values())) > 1}
    assert not mismatch, mismatch
    stats = {f'{family}/{size}/{solver}': aggregate(items, 10 if family == 'jobshop' else 3)
             for (family, size, solver), items in by_group.items()}
    report = dict(expected_calls=993, completed_calls=len(rows),
                  complete=len(found) == 993, instances_with_proofs=len(objective),
                  calls_by_solver=dict(collections.Counter(r['solver'] for r in rows)),
                  statuses=dict(collections.Counter(r['status'] for r in rows)),
                  objective_mismatches=mismatch, statistics=stats,
                  missing=[dict(instance=n, solver=s) for n, s in sorted(expected - found)])
    (OUT / 'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ['expected_calls', 'completed_calls', 'complete',
          'calls_by_solver', 'statuses', 'objective_mismatches']}, ensure_ascii=False))
    if args.require_complete and not report['complete']:
        raise SystemExit('The manuscript matrix is still incomplete.')
    if report['complete']:
        (OUT / 'results.json').write_text(json.dumps(rows, indent=2))
        fields = ['name', 'family', 'category', 'size', 'seed', 'paradigm', 'solver',
                  'status', 'proved_optimal', 'objective', 'runtime_s', 'memory_peak_mb', 'timeout_s']
        with (OUT / 'results.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    tables = OUT / 'tables'
    tables.mkdir(exist_ok=True)
    if all(stats.get(f'{f}/{n}/{solver}', {}).get('completed') == 3 for f, _, sizes in FAMILIES for n in sizes for solver in LINEAR):
        lines = []
        for fi, (family, label, sizes) in enumerate(FAMILIES):
            if fi:
                lines.append(r'\midrule')
            for size in sizes:
                lines.append(label + r'\,' + str(size) + ' & ' + ' & '.join(
                    cell(stats[f'{family}/{size}/{s}'], s, 3) for s in LINEAR) + r' \\')
        (tables / 'linear.tex').write_text('\n'.join(lines) + '\n')
    if not all(stats.get(f'jobshop/{n}/{solver}', {}).get('completed') == 10 for n in [7, 8, 9, 10] for solver in JOB):
        return
    lines = [str(n) + ' & ' + ' & '.join(cell(stats[f'jobshop/{n}/{s}'], s, 10)
             for s in JOB) + r' \\' for n in [7, 8, 9, 10]]
    (tables / 'jobshop.tex').write_text('\n'.join(lines) + '\n')
    labels = {'z3': r'$\nu Z$', 'optimathsat': 'OptiMathSAT',
              'cbc-bigm': r'CBC (大-$M$)', 'cpsat': 'CP-SAT'}
    lines = []
    for n in [8, 10]:
        for solver, label in labels.items():
            st = stats[f'jobshop/{n}/{solver}']
            med = f"{st['median']:.3f}" if st['median'] is not None else 'T/O'
            iqr = f"[{st['q1']:.3f}, {st['q3']:.3f}]" if st['q1'] is not None else '--'
            if st['success_min'] is None:
                span = '--'
            elif st['success_min'] == st['success_max']:
                span = f"{st['success_min']:.3f}"
            else:
                span = f"{st['success_min']:.3f}--{st['success_max']:.3f}"
            lines.append(f"{n} & {label} & {st['optimal']}/10 & {med} & {iqr} & {span}" + r'\\')
    (tables / 'spread.tex').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
