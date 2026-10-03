#!/usr/bin/env python3
"""Summarize all fixed public cases without dropping failures or censored runs."""
import collections
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/rx032_public'


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def main():
    selection = read(ROOT / 'benchmarks/public_fp/selection.json')
    rows = []
    for index, case in enumerate(selection['selected']):
        folder = OUT / f'{index:02d}'
        for form in ['fp', 'bvfp', 'bv']:
            solve = read(folder / (form + '.solve.json'))
            verify = read(folder / (form + '.verify.json'))
            assert solve, f'Missing result: {index} {form}'
            status = solve.get('status')
            reason = str(solve.get('reason', '')) + str(solve.get('stderr', ''))
            if verify.get('status') == 'verified' and 'NaN' not in str(verify.get('value')):
                category = 'verified_optimum'
            elif status in ['candidate', 'feasible']:
                category = 'unverified_candidate'
            elif 'memory' in reason.lower() or 'bad_alloc' in reason.lower():
                category = 'memory_limit'
            elif status == 'timeout' or 'timeout' in reason.lower() or 'canceled' in reason.lower():
                category = 'timeout'
            elif status == 'unknown':
                category = 'unknown'
            elif status == 'unsat':
                category = 'unsat'
            else:
                category = 'error'
            input_path = (ROOT / 'benchmarks/public_fp' / case['forms']['fp']['path']
                          if form == 'fp' else folder / (form + '.smt2'))
            rows.append(dict(index=index, group=case['group'], sense=case['sense'],
                upstream=case['upstream'], form=form, category=category,
                solver_status=status, verification_status=verify.get('status'),
                attainable=verify.get('attainable'), strictly_better=verify.get('strictly_better'),
                value=verify.get('value'),
                elapsed_s=solve.get('solve_s', solve.get('wall_s')),
                input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest() if input_path.exists() else None))
    assert len(rows) == 60
    with (OUT / 'summary.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    totals = {form: dict(collections.Counter(r['category'] for r in rows if r['form'] == form))
              for form in ['fp', 'bvfp', 'bv']}
    groups = {group: {form: sum(r['category'] == 'verified_optimum' for r in rows
                               if r['group'] == group and r['form'] == form)
                      for form in ['fp', 'bvfp', 'bv']}
              for group in sorted({r['group'] for r in rows})}
    result = dict(cases=20, formulations=60, counts=totals,
                  verified_by_group=groups,
                  rules='Every fixed case counted. A verified optimum requires SAT attainability and UNSAT strict improvement in original FP constraints. No timing ranking; encoding and implementation differ.')
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
