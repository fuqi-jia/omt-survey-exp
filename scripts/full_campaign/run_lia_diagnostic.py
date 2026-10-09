#!/usr/bin/env python3
"""Run every original multi-objective LIA companion without inventing bit bounds.

These are semantic diagnostics, not equivalent single-objective BV encodings.
SAT and a printed model are never promoted to an optimal-model claim here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import run_case as common
import z3

ROOT = common.ROOT


def objectives(text):
    result = re.findall(r'^\s*\((maximize|minimize)\s+([^\s()]+)\)\s*$', text, re.M)
    assert result, 'No simple named objective in the original LIA file'
    return result


def parse_input(path):
    text = path.read_text()
    targets = objectives(text)
    opt = z3.Optimize()
    opt.from_string(text)
    assert len(opt.objectives()) == len(targets)
    return opt, targets


def solve_z3(path):
    opt, targets = parse_input(path)
    opt.set(priority='lex', timeout=common.BUDGET*1000)
    start = time.monotonic()
    status = opt.check()
    record = dict(solver_status=str(status), solve_s=time.monotonic()-start,
                  objective_count=len(targets), priority='lex')
    if status == z3.unsat:
        return dict(record, status='diagnostic_infeasible')
    if status == z3.unknown:
        return dict(record, status='diagnostic_unknown', reason=opt.reason_unknown())
    bounds = []
    for i, (sense, term) in enumerate(targets):
        handle = z3.OptimizeObjective(opt, i, sense == 'maximize')
        bounds.append(dict(index=i, sense=sense, term=term,
                           lower=handle.lower().sexpr(), upper=handle.upper().sexpr()))
    unbounded = [r['index'] for r in bounds if 'oo' in r['lower'] or 'oo' in r['upper']]
    return dict(record, status='diagnostic_unbounded' if unbounded else 'diagnostic_finite_bounds',
                bounds=bounds, infinity_bound_objectives=unbounded,
                optimal_model_claimed=False)


def solve_oms(path, out):
    source = path.read_text()
    targets = objectives(source)
    # Preserve all declarations, constraints and objective order. Only response
    # commands and the explicit multi-objective mode are normalized.
    body = re.sub(r'^\s*\((?:check-sat|get-model|get-objectives|exit)\)\s*$', '', source, flags=re.M)
    text = '(set-option :produce-models true)\n' + body + '\n(check-sat)\n(get-objectives)\n(get-model)\n'
    with tempfile.TemporaryDirectory(prefix='lia-input-', dir=out) as temp:
        query = Path(temp) / 'input.smt2'
        query.write_text(text)
        command = [str(common.OMS), '-optimization=true', '-opt.priority=lex', str(query)]
        with (out/'oms_lia.native.stdout').open('w') as stdout, (out/'oms_lia.native.stderr').open('w') as stderr:
            start = time.monotonic()
            proc = subprocess.run(command, stdout=stdout, stderr=stderr)
            elapsed = time.monotonic()-start
    raw = (out/'oms_lia.native.stdout').read_text()
    status = re.search(r'^(sat|unsat|unknown)\s*$', raw, re.M)
    record = dict(solve_s=elapsed, solver_returncode=proc.returncode,
                  objective_count=len(targets), priority='lex',
                  normalized_sha256=hashlib.sha256(text.encode()).hexdigest(),
                  command=command[:-1]+['<normalized-response-commands>'])
    if proc.returncode or status is None or '(error' in raw[:status.start()]:
        return dict(record, status='solver_error')
    record['solver_status'] = status.group(1)
    record['post_status_query_error'] = '(error' in raw[status.end():]
    record['contains_infinity_marker'] = bool(re.search(r'\boo\b', raw))
    record['optimal_model_claimed'] = False
    return dict(record, status={'sat':'diagnostic_sat', 'unsat':'diagnostic_infeasible',
                                'unknown':'diagnostic_unknown'}[status.group(1)])


def worker(args):
    z3.set_param('parallel.enable', False)
    row = common.case_row(args.case)
    assert row['suite'] == 'bv_lia'
    path = ROOT / row['path']
    assert common.sha(path) == row['sha256']
    return solve_oms(path, Path(args.out)) if args.variant == 'oms_lia' else solve_z3(path)


def invoke(args, variant, out):
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--case', args.case,
               '--variant', variant, '--out', str(out)]
    start = time.monotonic()
    stdout_path = out/(variant+'.solve.stdout')
    stderr_path = out/(variant+'.solve.stderr')
    with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
        proc = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True,
            preexec_fn=common.limits, env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        try:
            proc.wait(timeout=common.BUDGET)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            timed_out = True
    record = dict(returncode=proc.returncode, wall_s=time.monotonic()-start,
                  budget_s=common.BUDGET, command=command,
                  status='timeout' if timed_out else 'worker_error')
    if not timed_out and proc.returncode == 0:
        try:
            record.update(json.loads(stdout_path.read_text().splitlines()[-1]))
        except (ValueError, IndexError):
            record['status'] = 'output_error'
    elif not timed_out and any(s in stderr_path.read_text() for s in ['out of memory','MemoryError','std::bad_alloc','failed to allocate']):
        record['status'] = 'oom'
    evidence = out/(variant+'.json')
    evidence.write_text(json.dumps(record, indent=2)+'\n')
    summary = dict(record)
    if 'bounds' in summary:
        summary['bounds_count'] = len(summary.pop('bounds'))
        summary['infinity_bound_count'] = len(summary.pop('infinity_bound_objectives'))
        summary['full_bounds_file'] = evidence.name
        summary['full_bounds_sha256'] = common.sha(evidence)
    return summary


def main(args):
    expected = os.environ.get('EOS_PARAM_HARNESS_SHA256')
    if expected:
        assert common.sha(Path(__file__)) == expected
    expected_common = os.environ.get('EOS_PARAM_COMMON_SHA256')
    if expected_common:
        assert common.sha(Path(common.__file__)) == expected_common
    row = common.case_row(args.case)
    assert row['suite'] == 'bv_lia'
    out = Path(args.out or os.environ['EOS_RUN_DIR'])/'evidence'
    out.mkdir(parents=True, exist_ok=True)
    variants = ['oms_lia','z3_lia']
    if int(row['id'][-1],16)%2:
        variants.reverse()
    provenance = dict(input=row, variants=variants, hostname=platform.node(), platform=platform.platform(),
        python=sys.version, z3=z3.get_version_string(), z3_binary_sha256=common.sha(Path(z3.__file__).parent/'lib/libz3.so'),
        oms_sha256=common.sha(common.OMS), script_sha256=common.sha(Path(__file__)),
        common_source_sha256=common.sha(Path(common.__file__)),
        parser_source_sha256=common.sha(ROOT/'scripts/revision_public_fp.py'),
        budget_s=common.BUDGET, verification_query_budget_s=0, memory_bytes=common.MEMORY,
        cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),'unknown'),
        scope='Original multi-objective LIA diagnostic; lexicographic input order; no inferred bit bounds; not a BV-equivalent performance comparison',
        verification='No optimal-model claim; raw bounds/status/model output retained without conflating SAT with optimality')
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    start = time.monotonic()
    results = {v: invoke(args,v,out) for v in variants}
    metrics = dict(completed=True, pipeline_ok=all(r['status'] not in {'worker_error','output_error','solver_error'} for r in results.values()),
                   case=row['id'], suite='bv_lia', solver_runs=2, wall_time_s=time.monotonic()-start,
                   diagnostic_only=True, results=results)
    Path(args.metrics or os.environ['EOS_METRICS_FILE']).write_text(json.dumps(metrics, indent=2)+'\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--worker', action='store_true')
    ap.add_argument('--variant', choices=['oms_lia','z3_lia'])
    ap.add_argument('--out')
    ap.add_argument('--metrics')
    args = ap.parse_args()
    if args.worker:
        print(json.dumps(worker(args)))
    else:
        main(args)
