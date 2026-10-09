#!/usr/bin/env python3
"""Export this campaign only; reconcile every platform row with frozen inputs.

Run on the control host. A snapshot is progress evidence, never a completed
benchmark table unless all inputs have all expected solver observations.
"""
import collections
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/full-python'))
OUT = ROOT / 'runs/full20261009'
VARIANTS = {
    'fp': ['oms_fp', 'z3_fpkey', 'z3_bv'],
    'bv': ['oms_bv', 'z3_bv'],
    'bv_lia': ['oms_lia', 'z3_lia'],
    'maxsmt': ['oms_maxres', 'oms_omt', 'z3_maxres', 'z3_wmax'],
}
ACTIVE = {'pending', 'assigned', 'running'}


def canonical_value(suite, variant, value):
    if suite != 'fp':
        if value['kind'] == 'bv':
            return ('integer', int(value['hex'], 16))
        return ('smt', value['literal'])
    if variant.startswith('z3'):
        width = value['width']
        key = int(value['hex'], 16)
        sign = 1 << (width - 1)
        bits = key ^ sign if key & sign else ~key & ((1 << width) - 1)
    else:
        import z3
        literal = value['literal']
        fp = z3.parse_smt2_string('(assert (= ' + literal + ' ' + literal + '))')[0].arg(0)
        width = fp.sort().ebits() + fp.sort().sbits()
        sign = 1 << (width - 1)
        bits = z3.simplify(z3.fpToIEEEBV(fp)).as_long()
    # Native FP numeric objectives tie the two zeros. Key objectives refine
    # that tie, so a signed-zero difference is not a value disagreement.
    if bits & (sign - 1) == 0:
        bits = 0
    return ('ieee', width, bits)


def main():
    con = sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    # A read transaction keeps the experiment and its run rows consistent.
    con.execute('begin')
    observed = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summary = {'observed_utc': observed, 'experiments': []}
    OUT.mkdir(parents=True, exist_ok=True)
    for exp in con.execute("select * from experiment where name like 'jos-full-%-20261009-%' order by name"):
        exp = dict(exp)
        suite = exp['name'].split('jos-full-', 1)[1].split('-20261009-', 1)[0]
        manifest_path = ROOT / 'benchmarks/full_public/manifests' / (suite + '.jsonl')
        manifest_data = manifest_path.read_bytes()
        manifest = [json.loads(line) for line in manifest_data.splitlines()]
        planned = {r['id']: r for r in manifest}
        runs = [dict(r) for r in con.execute('select * from run where experiment_id=? order by input', (exp['id'],))]
        snapshot = {'observed_utc': observed, 'experiment': exp, 'runs': runs}
        target = OUT / (suite + '-platform.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(target)
        counts = collections.Counter(r['status'] for r in runs)
        coverage = collections.Counter()
        outcomes = {v: collections.Counter() for v in VARIANTS[suite]}
        records, errors, disagreements = [], [], []
        for run in runs:
            meta = json.loads(run.get('input_meta_json') or '{}')
            case_id = meta.get('case_id')
            if case_id not in planned:
                errors.append({'run': run['id'], 'error': 'unplanned input', 'case': case_id})
                continue
            coverage[case_id] += 1
            if meta.get('source_sha256') != planned[case_id]['sha256']:
                errors.append({'run': run['id'], 'error': 'input hash mismatch'})
            metrics = json.loads(run.get('metrics_json') or '{}')
            results = metrics.get('results', {})
            if metrics and (metrics.get('case') != case_id or metrics.get('suite') != suite):
                errors.append({'run': run['id'], 'error': 'result/input identity mismatch'})
            if run['status'] not in ACTIVE and set(results) != set(VARIANTS[suite]):
                errors.append({'run': run['id'], 'error': 'terminal run lacks expected configurations'})
            values = {v: canonical_value(suite, v, r['value']) for v, r in results.items()
                      if r.get('status') == 'solver_claimed_optimal' and 'value' in r}
            if len(set(values.values())) > 1:
                disagreements.append({'run': run['id'], 'case': case_id, 'values': values})
            if values and any(r.get('status') == 'infeasible' for r in results.values()):
                disagreements.append({'run': run['id'], 'case': case_id,
                                      'error': 'infeasible versus a claimed optimum'})
            for variant in VARIANTS[suite]:
                result = results.get(variant)
                if result is None:
                    continue
                status = result.get('status', 'missing_status')
                verification = result.get('verification', {}).get('status', 'not_attempted')
                outcomes[variant][status] += 1
                outcomes[variant]['verification:' + verification] += 1
                if status in {'worker_error', 'output_error', 'solver_error'} or verification == 'contradiction':
                    errors.append({'run': run['id'], 'case': case_id, 'variant': variant,
                                   'error': status, 'verification': verification})
                records.append(dict(case=case_id, path=planned[case_id]['path'],
                    sha256=planned[case_id]['sha256'], run=run['id'], host=run['host'],
                    variant=variant, status=status, verification=verification,
                    wall_s=result.get('wall_s'), solve_s=result.get('solve_s'),
                    value=json.dumps(result.get('value'), sort_keys=True)))
        missing = sorted(set(planned) - set(coverage))
        duplicates = {key: n for key, n in coverage.items() if n != 1}
        result = dict(suite=suite, experiment=exp['id'], planned_inputs=len(planned),
            manifest_sha256=hashlib.sha256(manifest_data).hexdigest(), platform_counts=dict(counts),
            observed_solver_runs=len(records), expected_solver_runs=len(planned)*len(VARIANTS[suite]),
            missing_inputs=missing, duplicate_inputs=duplicates, outcomes=outcomes, errors=errors,
            objective_disagreements=disagreements)
        result['all_inputs_completed'] = (not missing and not duplicates and not errors and not disagreements
            and not any(counts.get(s, 0) for s in ACTIVE)
            and len(records) == result['expected_solver_runs'])
        summary['experiments'].append(result)
        if records:
            with (OUT / (suite + '-results.csv')).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)
    con.rollback()
    target = OUT / 'coverage-progress.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
