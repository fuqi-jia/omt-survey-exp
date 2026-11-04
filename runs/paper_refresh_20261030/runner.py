#!/usr/bin/env python3
"""Rerun the manuscript's 97 performance instances, preserving archived runs.

Each process owns one physical core and launches one isolated, memory-limited
solver invocation at a time. Commercial backends are deliberately excluded;
the author runs those independently against this same manifest.
"""
import _bootstrap  # noqa: F401
import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

from experiments.benchmarks.families import build, FAMILIES
from experiments.encodings.smt2 import to_smt2
from experiments.encodings.minizinc import to_minizinc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/paper_refresh_20261028'
LINEAR = {'gap': [40, 80, 160, 320], 'knapsack': [40, 80, 160, 320, 640],
          'config': [40, 80, 150, 200, 300], 'setcover': [40, 80, 160, 240, 320]}
BASE = ['z3', 'optimathsat', 'cbc', 'highs', 'scip', 'gecode', 'cpsat']
JOBS = ['z3', 'optimathsat', 'cbc-bigm', 'highs-bigm', 'scip-bigm',
        'highs-hull', 'gecode', 'cpsat']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for family, sizes in {**LINEAR, 'jobshop': [7, 8, 9, 10]}.items():
        for size in sizes:
            for seed in range(10 if family == 'jobshop' else 3):
                spec = build(family, size, seed)
                name = f'{FAMILIES[family].category}_{family}_{size}_{seed}'
                row = dict(name=name, family=family, size=size, seed=seed,
                           category=FAMILIES[family].category,
                           sense=FAMILIES[family].sense, inputs={})
                for kind, text in [('smt2', to_smt2(spec)), ('mzn', to_minizinc(spec))]:
                    p = OUT / kind / (name + '.' + kind)
                    p.parent.mkdir(exist_ok=True)
                    data = text.encode()
                    if p.exists():
                        assert p.read_bytes() == data
                    else:
                        p.write_bytes(data)
                    row['inputs'][kind] = dict(path=p.relative_to(OUT).as_posix(), sha256=sha(p))
                rows.append(row)
    assert len(rows) == 97
    manifest = dict(instances=rows, timeout_s=600, memory_bytes=4 * 1024**3,
                    linear_seeds=[0, 1, 2], jobshop_seeds=list(range(10)))
    p = OUT / 'manifest.json'
    if p.exists():
        assert json.loads(p.read_text()) == manifest
    else:
        p.write_text(json.dumps(manifest, indent=2))
    return rows


def initialize(cores, output=None):
    global OUT
    if output:
        OUT = Path(output)
    idx = multiprocessing.current_process()._identity[0] - 1
    core = cores[idx % len(cores)]
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {core})
    else:
        import psutil
        psutil.Process().cpu_affinity([core])


def run_one(task):
    row, solver = task
    p = OUT / 'cells' / (row['name'] + '__' + solver + '.json')
    if p.exists():
        return json.loads(p.read_text())
    command = [sys.executable, str(ROOT / 'scripts/run_all.py'), '--solve-one',
               '--solver', solver, '--family', row['family'], '--size', str(row['size']),
               '--seed', str(row['seed']), '--timeout', '600', '--memgb', '4']
    for kind in ['smt2', 'mzn']:
        command.extend(['--' + kind, str(OUT / row['inputs'][kind]['path'])])
    start = time.monotonic()
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=(os.name != "nt"))
    guard_timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=630)
    except subprocess.TimeoutExpired:
        guard_timed_out = True
        if hasattr(os, 'killpg'):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            import psutil
            for child in psutil.Process(proc.pid).children(recursive=True):
                child.kill()
            proc.kill()
        stdout, stderr = proc.communicate()
    result = None
    for line in stdout.splitlines():
        if line.startswith('__RESULT__'):
            result = json.loads(line[len('__RESULT__'):])
    if result is None:
        result = dict(status='TIMEOUT' if guard_timed_out else 'ERROR',
                      proved_optimal=False, objective=None,
                      runtime_s=time.monotonic() - start,
                      error_message=None if guard_timed_out else
                          'isolated worker did not emit a result')
        if guard_timed_out:
            result.update(external_timeout_s=630,
                          termination_reason='external wall-time guard expired')
    result.update({k: v for k, v in row.items() if k != 'inputs'})
    result.update(solver=solver, wall_s=time.monotonic() - start,
                  command=command, returncode=proc.returncode,
                  cpu=(list(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else __import__('psutil').Process().cpu_affinity()))
    stem = p.with_suffix('')
    stem.with_suffix('.stdout').write_text(stdout)
    stem.with_suffix('.stderr').write_text(stderr)
    temporary = p.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(p)
    return result


def summarize():
    rows = [json.loads(p.read_text()) for p in sorted((OUT / 'cells').glob('*.json'))]
    mismatches = []
    by_name = {}
    for r in rows:
        if r.get('proved_optimal'):
            by_name.setdefault(r['name'], {})[r['solver']] = r['objective']
    for name, values in by_name.items():
        if len(set(values.values())) > 1:
            mismatches.append(dict(name=name, objectives=values))
    (OUT / 'results.json').write_text(json.dumps(rows, indent=2))
    (OUT / 'crosscheck.json').write_text(json.dumps(dict(mismatches=mismatches), indent=2))
    return len(rows), mismatches


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='runs/paper_refresh_20261028')
    ap.add_argument('--cores', help='comma-separated logical CPU ids')
    ap.add_argument('--solvers', help='comma-separated backend names')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--commercial', action='store_true', help='author-run Gurobi and CPLEX only')
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--prepare-only', action='store_true')
    args = ap.parse_args()
    OUT = ROOT / args.output
    rows = prepare()
    if args.prepare_only:
        print('Prepared 97 deterministic instances.'); return
    (OUT / 'cells').mkdir(exist_ok=True)
    if args.commercial:
        tasks = [(r, s) for r in rows for s in (['gurobi-bigm', 'cplex-bigm', 'gurobi-ind', 'cplex-ind'] if r['family'] == 'jobshop' else ['gurobi', 'cplex'])]
    else:
        tasks = [(r, s) for r in rows for s in (JOBS if r['family'] == 'jobshop' else BASE)]
    if args.solvers:
        wanted = set(args.solvers.split(','))
        tasks = [(r, s) for r, s in tasks if s in wanted]
    if args.smoke:
        tasks = [(r, s) for r, s in tasks if r['seed'] == 0 and
                 ((r['family'] == 'knapsack' and r['size'] == 40) or
                  (r['family'] == 'jobshop' and r['size'] == 7))]
    # Adjacent logical CPUs are siblings on the current host. Query sysfs rather
    # than assume their numbering, and reserve one logical CPU per physical core.
    if hasattr(os, 'sched_getaffinity'):
        unique = {}
        for c in sorted(os.sched_getaffinity(0)):
            t = Path(f'/sys/devices/system/cpu/cpu{c}/topology')
            key = ((t / 'physical_package_id').read_text(), (t / 'core_id').read_text())
            unique.setdefault(key, c)
        cores = list(unique.values())[:args.workers]
    else:
        import psutil
        cores = psutil.Process().cpu_affinity()[::2][:args.workers]
    if args.cores:
        cores = [int(x) for x in args.cores.split(',')]
        assert len(cores) == args.workers
    cpu = platform.processor()
    if Path('/proc/cpuinfo').exists():
        cpu = next(x.split(':', 1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
    environment = dict(hostname=platform.node(), platform=platform.platform(), python=sys.version,
                       cores=cores, solver_budget_s=600, memory_bytes=4 * 1024**3,
                       manifest_sha256=sha(OUT / 'manifest.json'), script_sha256=sha(Path(__file__)),
                       cpu=cpu)
    selected = set(args.solvers.split(',')) if args.solvers else set()
    if selected == {'z3'}:
        import shutil
        binary = Path(shutil.which('z3'))
        environment['z3'] = dict(version=subprocess.check_output([str(binary), '-version'], text=True).strip(), binary=str(binary), sha256=sha(binary))
    if args.commercial:
        cohort = 'commercial-cplex' if selected and all(s.startswith('cplex') for s in selected) else 'commercial-gurobi' if selected and all(s.startswith('gurobi') for s in selected) else 'commercial'
    else:
        cohort = 'z3-5.3.3' if selected == {'z3'} else 'open-scip' if selected and selected <= {'scip', 'scip-bigm'} else 'open-main'
    (OUT / ('environment-' + cohort + '.json')).write_text(json.dumps(environment, indent=2))
    print(json.dumps(dict(tasks=len(tasks), workers=len(cores), cpu=environment['cpu'])), flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(cores),
            mp_context=multiprocessing.get_context('spawn'), initializer=initialize,
            initargs=(cores, str(OUT))) as pool:
        for result in pool.map(run_one, tasks):
            print(json.dumps({k: result.get(k) for k in ['name', 'solver', 'status', 'runtime_s', 'error_message']}), flush=True)
    n, mismatches = summarize()
    print(json.dumps(dict(completed=n, crosscheck_mismatches=mismatches)), flush=True)


if __name__ == '__main__':
    main()
