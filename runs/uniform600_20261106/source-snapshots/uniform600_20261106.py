#!/usr/bin/env python3
"""Fresh 600-second numerical/NRA runs; previous cohorts remain unchanged."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get('OMT_UNIFORM600_OUTPUT', 'runs/uniform600_20261106')
LIMIT = 600


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def configure():
    os.environ['OMT_NRA_TIMEOUT_S'] = str(LIMIT)
    os.environ['OMT_NRA_WITNESS_TIMEOUT_S'] = str(LIMIT)
    for key, folder in [('PUBLIC', 'nra_public'), ('DISJ', 'nra_disjunctive'),
                        ('IRR', 'nra_irrational'), ('EXT', 'nra_extensions')]:
        os.environ[f'OMT_NRA_{key}_OUTPUT'] = str(OUT / folder)
    for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
        os.environ[key] = '1'


def prepare():
    for old, new in [('nra_public_20261102', 'nra_public'),
                     ('nra_disjunctive_20261102', 'nra_disjunctive'),
                     ('nra_irrational_20261102', 'nra_irrational')]:
        source = ROOT / 'runs' / old
        target = OUT / new
        manifest = []
        for path in sorted((source / 'models').glob('*.json')):
            data = path.read_bytes()
            dest = target / 'models' / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            manifest.append(dict(name=path.stem, sha256=hashlib.sha256(data).hexdigest()))
        protocol = json.loads((source / 'protocol.json').read_text())
        save(target / 'model-definition-protocol.json', protocol)
        if 'date' in protocol:
            protocol['model_definition_date'] = protocol.pop('date')
        if 'script_sha256' in protocol:
            protocol['model_generator_script_sha256'] = protocol.pop('script_sha256')
        protocol['execution_date'] = time.strftime('%Y-%m-%d')
        protocol['model_definition_protocol'] = 'model-definition-protocol.json'
        protocol['worker_script_sha256'] = hashlib.sha256(
            (ROOT / 'scripts' / (old + '.py')).read_bytes()).hexdigest()
        protocol.update(timeout_s=LIMIT, time_limit_s=LIMIT, memory_gb=4, threads=1,
                        model_manifest=manifest, archived_model_source=str(source.relative_to(ROOT)),
                        witness_query_timeout_s=LIMIT)
        save(target / 'protocol.json', protocol)
    save(OUT / 'protocol.json', dict(timeout_s=LIMIT, memory_gb=4, threads=1,
         candidate_collection='final interface/solution-file vector; no optimizer restart',
         source_scripts={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in Path(__file__).parent.glob('*.py')}))


def worker(kind, solver, name, core, start):
    configure()
    policy = OUT / 'affinity-policy.json'
    if policy.exists():
        mapping = json.loads(policy.read_text()).get('parent_pools', {}).get(str(os.getppid()), {})
        core = int(mapping.get(str(core), core))
    os.environ['OMT_NRA_CORE'] = str(core)
    if kind != 'numeric':
        claim = OUT / 'claims' / (kind + '__' + solver + '__' + name + '__' + start)
        claim.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            print('ALREADY_CLAIMED', kind, solver, name, start, flush=True)
            return
        with os.fdopen(fd, 'w') as handle:
            json.dump(dict(pid=os.getpid(), started=time.time(), core=core), handle)
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {core})
    else:
        import psutil
        psutil.Process().cpu_affinity([core])
    from memory_limit import limit_memory
    limit_memory(4)
    import nra_public_20261102 as common
    if kind == 'public':
        if solver == 'gurobi':
            import nra_public_gurobi_20261102 as mod
            mod.main()
        else:
            common.worker(solver, name, core)
    elif kind == 'disjunctive':
        import nra_disjunctive_20261102 as mod
        mod.gurobi() if solver == 'gurobi' else mod.worker(solver, name, core)
    elif kind == 'irrational':
        import nra_irrational_20261102 as mod
        if solver == 'gurobi':
            import nra_irrational_gurobi_20261102 as gurobi
            gurobi.main()
        else:
            mod.worker(solver, name, core, start)
    elif kind == 'extensions':
        import nra_numeric_extensions_20261102 as mod
        sys.argv = [mod.__file__, '--solver', solver, '--core', str(core)]
        mod.main()
    elif kind == 'base':
        import nra_refresh_20261028 as mod
        mod.OUT = OUT / 'nra_base'
        mod.OUT.mkdir(parents=True, exist_ok=True)
        mod.TIMEOUT_S = LIMIT
        if solver == 'scipy':
            import scipy.optimize as opt
            original_minimize = opt.minimize
            elapsed_calls = []
            def limited_minimize(*args, **kwargs):
                begun = time.monotonic()
                def callback(x):
                    if time.monotonic() - begun >= LIMIT:
                        raise TimeoutError('600-second optimization deadline')
                kwargs['callback'] = callback
                result = original_minimize(*args, **kwargs)
                elapsed_calls.append(time.monotonic() - begun)
                return result
            opt.minimize = limited_minimize
            mod.scipy_results()
            data = json.loads((mod.OUT / 'scipy.json').read_text())
            for row, elapsed in zip(data['records'], elapsed_calls):
                row.update(timeout_s=LIMIT, elapsed_s=elapsed)
            save(mod.OUT / 'scipy.json', data)
        elif solver == 'gurobi':
            code = mod.GUROBI_CODE.replace('__TIMEOUT_S__', str(LIMIT))
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                                    timeout=6 * LIMIT + 30)
            (mod.OUT / 'gurobi.stdout').write_text(result.stdout)
            (mod.OUT / 'gurobi.stderr').write_text(result.stderr)
            save(mod.OUT / 'gurobi.json', json.loads(result.stdout.splitlines()[-1]))
        else:
            record = mod.run_solver((solver, next(c for c in mod.CASES if c[0] == name)))
            save(mod.OUT / solver / (name + '.json'), record)
    elif kind == 'numeric':
        import diagnostics_refresh_20261028 as mod
        for cohort in ['exact', 'illcond']:
            if cohort == 'illcond' and solver in ['cpsat', 'scip-exact']:
                continue
            sys.argv = [mod.__file__, '--kind', cohort, '--solvers', solver,
                        '--timeout', str(LIMIT), '--core', str(core), '--output',
                        str((OUT / cohort / solver).relative_to(ROOT))]
            if solver in ['gurobi', 'cplex']:
                sys.argv.append('--commercial')
            mod.main()
    else:
        raise ValueError(kind)


def jobs():
    result = []
    for kind, solvers in [('public', ['z3', 'ocac', 'optimathsat', 'scipy', 'ipopt', 'couenne']),
                          ('disjunctive', ['z3', 'ocac', 'optimathsat', 'couenne']),
                          ('irrational', ['z3', 'ocac', 'optimathsat', 'couenne'])]:
        models = sorted((OUT / ('nra_' + kind) / 'models').glob('*.json'))
        for solver in solvers:
            result += [(kind, solver, path.stem, '') for path in models]
        result.append((kind, 'gurobi', 'all', ''))
    for path in sorted((OUT / 'nra_irrational/models').glob('*.json')):
        if not path.stem.startswith('C_'):
            result += [('irrational', solver, path.stem, start)
                       for solver in ['ipopt', 'scipy'] for start in ['I', 'II']]
    result += [('extensions', solver, 'all', '') for solver in ['ipopt', 'couenne']]
    import nra_refresh_20261028 as base
    result += [('base', solver, case[0], '')
               for solver in ['z3', 'ocac', 'optimathsat'] for case in base.CASES]
    result += [('base', solver, 'all', '') for solver in ['scipy', 'gurobi']]
    return result


def batch(workers, exclude_gurobi=False, selected_cores=None, pool_label="workers"):
    configure()
    # One logical CPU per physical core, within this process's allowed affinity.
    seen, cores = set(), []
    for cpu in sorted(os.sched_getaffinity(0)):
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        pair = ((topology / 'physical_package_id').read_text().strip(),
                (topology / 'core_id').read_text().strip())
        if pair not in seen:
            cores.append(cpu)
            seen.add(pair)
    cores = ([int(x) for x in selected_cores.split(",")] if selected_cores else cores[:workers])
    available = queue.Queue()
    for core in cores:
        available.put(core)
    work = [job for job in jobs() if not (exclude_gurobi and job[1] == "gurobi")]
    save(OUT / ('job_manifest-' + pool_label + '.json'), work)
    packages = {}
    for pkg in ['numpy', 'scipy', 'pyomo', 'gurobipy', 'z3-solver']:
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            pass
    save(OUT / ('environment-nra-' + pool_label + '.json'), dict(hostname=os.uname().nodename, python=sys.version,
         cores=cores, packages=packages, timeout_s=LIMIT, memory_gb=4,
         cpuinfo=Path('/proc/cpuinfo').read_text(), meminfo=Path('/proc/meminfo').read_text()))
    def run(job):
        kind, solver, name, start = job
        core = available.get()
        folder = OUT / pool_label / (kind + '__' + solver + '__' + name + '__' + start)
        folder.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, __file__, 'worker', '--kind', kind, '--solver', solver,
                   '--name', name, '--core', str(core), '--start', start]
        begun = time.monotonic()
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=2 * LIMIT + 90)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        (folder / 'stdout.txt').write_text(stdout)
        (folder / 'stderr.txt').write_text(stderr)
        record = dict(job=job, command=command, core=core, returncode=proc.returncode,
                      watchdog_timeout=timed_out, wall_s=time.monotonic() - begun)
        save(folder / 'process.json', record)
        available.put(core)
        print('DONE', job, proc.returncode, round(record['wall_s'], 2), flush=True)
        return record
    records = []
    with ThreadPoolExecutor(max_workers=len(cores)) as pool:
        for future in as_completed([pool.submit(run, job) for job in work]):
            records.append(future.result())
            save(OUT / ('worker_results-' + pool_label + '.json'), records)
    print('ALL_DONE', len(records), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'worker', 'batch'])
    parser.add_argument('--kind')
    parser.add_argument('--solver')
    parser.add_argument('--name', default='all')
    parser.add_argument('--core', type=int, default=0)
    parser.add_argument('--start', default='')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--exclude-gurobi', action='store_true')
    parser.add_argument('--cores')
    parser.add_argument('--pool-label', default='workers')
    args = parser.parse_args()
    configure()
    if args.mode == 'prepare':
        prepare()
    elif args.mode == 'batch':
        batch(args.workers, args.exclude_gurobi, args.cores, args.pool_label)
    else:
        worker(args.kind, args.solver, args.name, args.core, args.start)


if __name__ == '__main__':
    main()
