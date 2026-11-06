#!/usr/bin/env python3
"""Refresh the exactness and Hilbert tables without changing archived data."""
import _bootstrap  # noqa: F401
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import exact_experiment as exact
import illcond_experiment as illcond

ROOT = Path(__file__).resolve().parents[1]
OPEN = {'z3', 'optimathsat', 'cpsat', 'cbc', 'highs', 'scip', 'scip-exact'}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def invoke(out, kind, solver, n, timeout, exp=None, seed=None):
    tag = f'{exp}_{n}_{seed}__{solver}' if kind == 'exact' else f'{n}__{solver}'
    command = [sys.executable, __file__, '--kind', kind, '--worker',
               '--solver', solver, '--n', str(n), '--timeout', str(timeout)]
    if exp is not None:
        command.extend(['--exp', str(exp), '--seed', str(seed)])
    start = time.monotonic()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 30)
    raw = out / 'raw'
    raw.mkdir(exist_ok=True)
    (raw / (tag + '.stdout')).write_text(proc.stdout)
    (raw / (tag + '.stderr')).write_text(proc.stderr)
    save(raw / (tag + '.process.json'), dict(returncode=proc.returncode,
         wall_s=time.monotonic() - start, command=command))
    for line in proc.stdout.splitlines():
        if line.startswith('__DIAGNOSTIC__'):
            return json.loads(line[len('__DIAGNOSTIC__'):])
    raise RuntimeError(f'{tag}: no diagnostic result: {proc.stderr[-500:]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--core', type=int, help='dedicated logical CPU')
    ap.add_argument('--solvers', help='comma-separated selected backends')
    ap.add_argument('--commercial', action='store_true')
    ap.add_argument('--kind', choices=['exact', 'illcond'], required=True)
    ap.add_argument('--worker', action='store_true')
    ap.add_argument('--solver')
    ap.add_argument('--n', type=int)
    ap.add_argument('--exp', type=int)
    ap.add_argument('--seed', type=int)
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--output', help='result directory relative to repository root')
    args = ap.parse_args()
    os.environ['OMT_DIAGNOSTIC_TIMEOUT_S'] = str(args.timeout)
    exact.TIMEOUT_S = illcond.TIMEOUT_S = args.timeout
    if args.core is not None:
        if hasattr(os, 'sched_setaffinity'):
            os.sched_setaffinity(0, {args.core})
        else:
            import psutil
            psutil.Process().cpu_affinity([args.core])
    if args.worker:
        # Load one native backend per process. In particular, OR-Tools and
        # HiGHS ship different C++ libraries and must not share a diagnostic
        # interpreter or a failed optional import can masquerade as refusal.
        try:
            if args.kind == 'exact':
                fn = next(f for name, _, f in exact.SOLVERS if name == args.solver)
                result = fn(exact.gen(args.n, args.seed, 2**args.exp))
            else:
                fn = next(f for name, _, f in illcond.SOLVERS if name == args.solver)
                result = fn(args.n)
        except Exception as ex:
            result = dict(status='refused' if args.solver == 'cpsat' and
                          isinstance(ex, (OverflowError, ValueError, TypeError)) else 'error',
                          note=repr(ex))
        print('__DIAGNOSTIC__' + json.dumps(result), flush=True)
        return
    names = {'gurobi', 'cplex'} if args.commercial else OPEN
    if args.solvers:
        names = names.intersection(args.solvers.split(','))
    out = ROOT / args.output if args.output else ROOT / 'runs' / (args.kind + '_refresh_20261029')
    out.mkdir(parents=True, exist_ok=True)
    suffix = 'commercial' if args.commercial else 'open'
    versions = {}
    for package in ['z3-solver', 'highspy', 'pyscipopt', 'ortools', 'pulp', 'gurobipy', 'cplex']:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    environment = dict(hostname=platform.node(), python=sys.version,
                       platform=platform.platform(), packages=versions,
                       timeout_s=args.timeout,
                       scip_exact=os.environ.get('SCIP_EXACT'), cbc=os.environ.get('CBC_BIN'))
    label = suffix + ('-' + '-'.join(sorted(names)) if args.solvers else '')
    save(out / ('environment-' + label + '.json'), environment)
    results_path = out / ('results-' + suffix + '.json')
    previous = json.loads(results_path.read_text()) if results_path.exists() else []
    if args.kind == 'exact':
        old = {(r['exp'], r['n'], r['seed']): r for r in previous}
        rows = []
        for e in exact.EXPONENTS:
            for n in exact.SIZES:
                for seed in exact.SEEDS:
                    inst = exact.gen(n, seed, 2**e)
                    rec = dict(exp=e, n=n, seed=seed, true_opt=inst['opt'],
                               solvers=dict(old.get((e, n, seed), {}).get('solvers', {})))
                    for name, _, fn in exact.SOLVERS:
                        if name in names:
                            rec['solvers'][name] = invoke(out, 'exact', name, n, args.timeout, e, seed)
                    rows.append(rec)
                    save(out / ('results-' + suffix + '.json'), rows)
                    print(e, n, seed, {k: v['status'] for k, v in rec['solvers'].items()}, flush=True)
    else:
        rows = [r for r in previous if r['solver'] not in names]
        for name, paradigm, fn in illcond.SOLVERS:
            if name not in names:
                continue
            rec = dict(solver=name, paradigm=paradigm, by_n={})
            for n in illcond.SIZES:
                rec['by_n'][str(n)] = invoke(out, 'illcond', name, n, args.timeout)
            rows.append(rec)
            save(out / ('results-' + suffix + '.json'), rows)
            print(name, rec['by_n'], flush=True)


if __name__ == '__main__':
    main()
