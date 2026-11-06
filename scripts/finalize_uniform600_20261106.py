#!/usr/bin/env python3
"""Wait for the complete local cohort, then run the independent audits."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from uniform600_20261106 import ROOT, OUT, configure, save


def ready():
    for kind, solvers in [('public', ['z3', 'ocac', 'optimathsat', 'scipy', 'ipopt', 'couenne', 'gurobi']),
                          ('disjunctive', ['z3', 'ocac', 'optimathsat', 'couenne', 'gurobi']),
                          ('irrational', ['z3', 'ocac', 'optimathsat', 'couenne', 'gurobi'])]:
        folder = OUT / ('nra_' + kind)
        for model_path in (folder / 'models').glob('*.json'):
            model = json.loads(model_path.read_text())
            labels = solvers + (['scipy_I', 'scipy_II', 'ipopt_I', 'ipopt_II']
                                if kind == 'irrational' and model['family'] != 'C' else [])
            for solver in labels:
                path = folder / solver / model['name'] / 'result.json'
                if not path.exists():
                    return False
                try:
                    row = json.loads(path.read_text())
                except json.JSONDecodeError:
                    return False
                if kind == 'irrational' and 'optimization_hit' not in row:
                    return False
    import nra_refresh_20261028 as base
    required = [OUT / 'nra_base' / s / (c[0] + '.json')
                for s in ['z3', 'ocac', 'optimathsat'] for c in base.CASES]
    required += [OUT / 'nra_base' / (s + '.json') for s in ['scipy', 'gurobi']]
    required += [OUT / 'nra_extensions' / (s + '.json') for s in ['ipopt', 'couenne']]
    return all(p.exists() for p in required)


def main():
    configure()
    while not ready():
        time.sleep(30)
    time.sleep(3)
    logdir = OUT / 'audits'
    logdir.mkdir(exist_ok=True)
    names = ['recover_nra_solution_files_20261102.py', 'audit_nra_public_20261102.py',
             'audit_nra_disjunctive_20261102.py', 'audit_nra_irrational_20261102.py',
             'audit_uniform600_20261106.py', 'render_uniform600_20261106.py']
    for name in names:
        command = [sys.executable, str(ROOT / 'scripts' / name)]
        with (logdir / (name + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(name + ': see ' + str(logdir / (name + '.log')))
    snapshots = OUT / 'source-snapshots'
    for path in (ROOT / 'scripts').glob('*.py'):
        if ('nra_' in path.name or 'uniform600' in path.name or
            path.name in ['optimathsat_state600_20261106.py', 'review_diagnostics_20261104.py',
                          'diagnostics_refresh_20261028.py', 'exact_experiment.py',
                          'illcond_experiment.py', 'memory_limit.py']):
            (snapshots / path.name).write_bytes(path.read_bytes())
    protocol = json.loads((OUT / 'protocol.json').read_text())
    protocol['source_scripts'] = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in snapshots.glob('*.py')}
    protocol['auxiliary_api_calls'] = 2
    save(OUT / 'protocol.json', protocol)
    save(OUT / 'finalization.json', dict(passed=True, primary_calls=863, auxiliary_api_calls=2,
         timeout_s=600, execution='local', audits=names, finished_epoch=time.time()))
    print('ALL_AUDITS_PASSED', flush=True)


if __name__ == '__main__':
    main()
