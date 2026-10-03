#!/usr/bin/env python3
"""Audit the rx032 revision against immutable historical runs; never rewrite them."""
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.benchmarks.families import spec_jobshop, jobshop_ops
from experiments.encodings.smt2 import jobshop_smt2
from experiments.encodings.minizinc import jobshop_mzn
from experiments.encodings.milp_gdp import build_transformed
from pyomo.environ import TransformationFactory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT / 'runs' / 'rx032_audit'
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'runs' / run / 'results.json' for run in ('long600', 'jobshop_seeds')]
    baseline = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    rows = []
    for p in sources:
        rows.extend(dict(r, run=p.parent.name) for r in json.loads(p.read_text())
                    if (p.parent.name == 'jobshop_seeds' or r['family'] != 'jobshop'))
    instances = collections.defaultdict(list)
    groups = collections.defaultdict(list)
    for r in rows:
        instances[r['name']].append(r)
        groups[(r['run'], r['family'], r['size'], r['solver'])].append(r)
    disagreements = []
    for name, rs in instances.items():
        values = {r['objective'] for r in rs if r['proved_optimal']}
        if len(values) != 1:
            disagreements.append({'name': name, 'values': sorted(values)})
    assert len(instances) == 97 and not disagreements
    summaries = []
    for (run, family, n, solver), rs in sorted(groups.items()):
        assert len({r['seed'] for r in rs}) == len(rs)
        times = sorted(r['runtime_s'] if r['proved_optimal'] else math.inf for r in rs)
        q1, _, q3 = statistics.quantiles(times, n=4, method='inclusive') if all(map(math.isfinite, times)) else (None, None, None)
        good = [r['runtime_s'] for r in rs if r['proved_optimal']]
        summaries.append(dict(run=run, family=family, size=n, solver=solver, seeds=len(rs),
            optimal=len(good), median_all_seeds=statistics.median(times),
            q1_all_solved=q1, q3_all_solved=q3,
            min_solved=min(good) if good else None, max_solved=max(good) if good else None,
            status_counts=json.dumps(dict(collections.Counter(r['status'] for r in rs))),
            per_seed=json.dumps([{k:r.get(k) for k in ('seed','status','proved_optimal','runtime_s','objective','source','reused_from')} for r in sorted(rs,key=lambda x:x['seed'])])))
    with (out / 'seed-distributions.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0])); w.writeheader(); w.writerows(summaries)

    checks = []
    for n in range(7, 11):
        for seed in range(10):
            spec = spec_jobshop(n, seed)
            H = spec['H']; ops = jobshop_ops(spec)
            assert H == sum(o['dur'] for o in ops) and all(2 <= o['dur'] <= 9 for o in ops)
            name = f'B_jobshop_{n}_{seed}'
            smt = jobshop_smt2(spec)
            mzn = jobshop_mzn(spec)
            paths = [(ROOT/'runs/jobshop_seeds/smt2'/f'{name}.smt2', smt),
                     (ROOT/'runs/jobshop_seeds/mzn'/f'{name}.mzn', mzn)]
            matches = {}
            for p, text in paths:
                if p.exists():
                    assert p.read_text() == text, f'historical input changed: {p}'
                    matches[p.suffix] = sha(p)
            assert '.smt2' in matches
            m = build_transformed(spec)
            assert all(v.is_integer() and v.lb == 0 and v.ub == H for v in m.st.values())
            assert m.mk.is_integer() and m.mk.lb == 0 and m.mk.ub == H
            Ms = TransformationFactory('gdp.bigm').get_all_M_values_by_constraint(m)
            assert all(lo is None and H+2 <= hi <= H+9 for lo, hi in Ms.values())
            checks.append(dict(name=name, H=H, inputs=matches,
                               min_auto_M=min(v[1] for v in Ms.values()),
                               max_auto_M=max(v[1] for v in Ms.values())))

    # The archived big-M reconstruction uses variable-box bounds, not makespan-derived bounds.
    # For each branch s_i+d_i <= s_j, its maximum violation on [0,H]^2 is H+d_i.
    # Under the full scheduling constraints, s_i+d_i <= Cmax <= H implies violation <= H.
    assert baseline == {str(p.relative_to(ROOT)): sha(p) for p in sources}
    report = dict(source_sha256=baseline, compared_instances=len(instances),
                  optimal_objective_disagreements=disagreements,
                  regenerated_jobshop_checks=checks,
                  conclusion='Nonnegative integer times are present. Pyomo automatic M is H+d_i; hand-written PuLP M is H.',
                  quantiles='Inclusive linear interpolation; IQR only when all seeds proved optimal. All-seed median ranks every unproved run at +infinity.',
                  limitations='Matching objective values are a consistency check, not a proof of general encoding equivalence.')
    (out/'audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k:report[k] for k in ('compared_instances','optimal_objective_disagreements','conclusion')},ensure_ascii=False))
    print('Verified historical job-shop encodings:',len(checks))


if __name__ == '__main__':
    main()
