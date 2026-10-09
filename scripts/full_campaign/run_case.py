#!/usr/bin/env python3
"""One complete input, paired solver runs, bounded independent optimality queries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/full-python'))
sys.path.insert(0, str(ROOT/'scripts'))
from revision_public_fp import split_commands
DATA = ROOT/'benchmarks/full_public'
OMS = ROOT/'tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat'
BUDGET = 600
VERIFY = 60
MEMORY = 8*1024**3
COST = '__jos20261009_cost'
if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(1024*1024):
            h.update(b)
    return h.hexdigest()


def case_row(case):
    suite, offset = case.split('@')
    assert suite in {'fp', 'bv', 'bv_lia', 'maxsmt'}
    with (DATA/'manifests'/(suite+'.jsonl')).open('rb') as f:
        f.seek(int(offset))
        row = json.loads(f.readline())
    assert row['suite'] == suite
    return row


def load_problem(row):
    import z3
    path = ROOT/row['path']
    assert sha(path) == row['sha256']
    text = path.read_text()
    assert COST not in text
    commands = list(split_commands(text))
    base, soft, objectives = [], [], []
    for command in commands:
        head = re.match(r'\(\s*([^\s()]+)', command).group(1)
        if head in {'minimize', 'maximize'}:
            m = re.fullmatch(r'\((minimize|maximize)\s+(.+)\)', command, re.S)
            objectives.append((m.group(1), m.group(2).strip()))
        elif head == 'assert-soft':
            m = re.fullmatch(r'\(assert-soft\s+(.+)\s+:weight\s+(\d+)\s+:id\s+([^\s()]+)\)', command, re.S)
            if not m:
                raise ValueError('Unrecognized soft assertion: '+command[:100])
            soft.append((m.group(1), int(m.group(2)), m.group(3)))
        elif head in {'check-sat', 'exit'} or head.startswith(('get-', 'set-')):
            continue
        else:
            base.append(command)
    assert len(objectives) == 1, objectives
    sense, term = objectives[0]
    if soft:
        assert row['suite'] == 'maxsmt'
        assert len({s[2] for s in soft}) == 1
        assert sense == 'minimize' and term == soft[0][2]
        assert all(w > 0 for _, w, _ in soft)
        terms = [f'(ite {s} 0 {w})' for s, w, _ in soft]
        term = '(+ '+' '.join(terms)+')' if len(terms)>1 else terms[0]
    base = '\n'.join(base)
    parsed = list(z3.parse_smt2_string(base+f'\n(assert (= {term} {term}))'))
    target, hard = parsed[-1].arg(0), parsed[:-1]
    definition = f'\n(define-fun {COST} () {target.sort().sexpr()} {term})\n'
    soft_expressions = []
    if soft:
        all_assertions = z3.parse_smt2_string(base+'\n'+'\n'.join(f'(assert {s})' for s, _, _ in soft))
        soft_expressions = list(all_assertions)[len(hard):]
        assert len(soft_expressions) == len(soft)
    return dict(base=base, definition=definition, target=target, hard=hard,
                soft=soft, soft_expressions=soft_expressions, sense=sense)


def value_json(value):
    import z3
    if z3.is_bv_value(value):
        return dict(kind='bv', hex=format(value.as_long(), 'x'), width=value.size())
    return dict(kind='smt', literal=value.sexpr())


def value_term(value):
    if value['kind'] == 'bv':
        return f'(_ bv{int(value["hex"],16)} {value["width"]})'
    return value['literal']


def fp_key(x):
    import z3
    bits = z3.fpToIEEEBV(x)
    width = x.sort().ebits()+x.sort().sbits()
    key = z3.BitVec('__jos20261009_fpkey', width)
    expr = z3.If(z3.Extract(width-1,width-1,bits)==1, ~bits,
                 bits ^ z3.BitVecVal(1 << (width-1), width))
    return key, expr


def native_oms(problem, row, variant, out):
    import z3
    base = problem['base']+problem['definition']
    if problem['soft']:
        base += '\n'.join(f'(assert-soft {s} :weight {w} :id __jos20261009_soft)' for s,w,_ in problem['soft'])
        objective = '__jos20261009_soft'
    else:
        objective = COST
    # Ordered FP objectives exclude NaN in every compared formulation. The
    # original file remains archived verbatim and its hash is part of the run.
    if row['suite'] == 'fp':
        base += f'\n(assert (not (fp.isNaN {COST})))\n'
    text = '(set-option :produce-models true)\n'+base+f'\n({problem["sense"]} {objective})\n(check-sat)\n(get-objectives)\n(get-value ({COST}))\n'
    command = [str(OMS), '-optimization=true']
    if variant == 'oms_maxres':
        command += ['-opt.maxsmt_engine=maxres', '-unsat_core_generation=1']
    with tempfile.TemporaryDirectory(prefix='input-', dir=out) as tmp:
        path=Path(tmp)/'problem.smt2';path.write_text(text)
        fingerprint=sha(path)
        with (out/(variant+'.native.stdout')).open('w') as stdout, (out/(variant+'.native.stderr')).open('w') as stderr:
            t=time.monotonic()
            run=subprocess.run(command+[str(path)], stdout=stdout, stderr=stderr)
            elapsed=time.monotonic()-t
    raw=(out/(variant+'.native.stdout')).read_text()
    result=dict(solve_s=elapsed, solver_returncode=run.returncode,
                normalized_sha256=fingerprint, command=command+['<normalized-input>'])
    unsat_match = re.search(r'^unsat\s*$',raw,re.M)
    if run.returncode == 0 and unsat_match and '(error' not in raw[:unsat_match.start()]:
        return dict(result, status='infeasible', post_unsat_query_error='(error' in raw[unsat_match.end():])
    if run.returncode or '(error' in raw:
        return dict(result, status='solver_error')
    if not re.search(r'^sat\s*$',raw,re.M):
        return dict(result, status='unknown')
    match=None
    for form in split_commands(raw):
        m=re.fullmatch(r'\(\s*\(\s*'+COST+r'\s+(.+)\)\s*\)',form,re.S)
        if m:
            match=m.group(1)
    if match is None:
        return dict(result, status='output_error')
    v=z3.Const('__jos_value',problem['target'].sort())
    parsed=z3.parse_smt2_string(f'(assert (= __jos_value {match}))',decls={'__jos_value':v})
    return dict(result,status='solver_claimed_optimal',value=value_json(parsed[0].arg(1)))


def solve_z3(problem,row,variant):
    import z3
    hard=problem['hard'];target=problem['target']
    start=time.monotonic();translate_s=0.0
    if row['suite']=='fp':
        key,expr=fp_key(target)
        hard=hard+[z3.Not(z3.fpIsNaN(target)),key==expr]
        target=key
        if variant=='z3_bv':
            goal=z3.Goal();goal.add(*hard)
            t=time.monotonic();subs=z3.Then('simplify','fpa2bv','simplify')(goal)
            translate_s=time.monotonic()-t
            assert len(subs)==1
            hard=list(subs[0])
    opt=z3.Optimize()
    opt.set(timeout=max(1,int((BUDGET-(time.monotonic()-start))*1000)))
    if problem['soft']:
        opt.set(maxsat_engine='wmax' if variant=='z3_wmax' else 'maxres')
    opt.add(*hard)
    if problem['soft']:
        for expr,(_,weight,_) in zip(problem['soft_expressions'],problem['soft']):
            handle=opt.add_soft(expr,weight=str(weight),id='__jos20261009_soft')
    else:
        handle=opt.minimize(target) if problem['sense']=='minimize' else opt.maximize(target)
    t=time.monotonic();r=opt.check();elapsed=time.monotonic()-t
    result=dict(status=str(r),solve_s=elapsed,translation_s=translate_s,
                objective_count=len(opt.objectives()))
    if r==z3.unsat:
        return dict(result,status='infeasible')
    if r==z3.unknown:
        return dict(result,status='unknown',reason=opt.reason_unknown())
    value=opt.model().eval(target,model_completion=True)
    lower,upper=handle.lower(),handle.upper()
    # Complete equal bounds, not SAT alone, are required for optimality.
    result['bounds_equal']=z3.eq(lower,upper)
    result['value']=value_json(value)
    if z3.is_bv_value(value):
        agrees=z3.is_int_value(lower) and lower.as_long()==value.as_long()
    else:
        agrees=z3.is_true(z3.simplify(value==lower))
    result['status']='solver_claimed_optimal' if result['bounds_equal'] and agrees else 'feasible'
    if row['suite']=='fp':
        result['value_semantics']='unsigned IEEE ordinal key; non-NaN; -0 precedes +0'
    return result


def verify(problem,row,variant,record):
    import z3
    target=problem['target'];hard=problem['hard']
    value=record['value']
    if row['suite']=='fp' and variant.startswith('z3'):
        key,expr=fp_key(target);target=expr
        hard=hard+[z3.Not(z3.fpIsNaN(problem['target']))]
    elif row['suite']=='fp':
        hard=hard+[z3.Not(z3.fpIsNaN(target))]
    v=z3.Const('__jos_value',target.sort())
    parsed=z3.parse_smt2_string(f'(assert (= __jos_value {value_term(value)}))',decls={'__jos_value':v})
    val=parsed[0].arg(1)
    if z3.is_bv(target):
        better=z3.ULT(target,val) if problem['sense']=='minimize' else z3.UGT(target,val)
    elif z3.is_fp(target):
        better=z3.fpLT(target,val) if problem['sense']=='minimize' else z3.fpGT(target,val)
    else:
        better=target<val if problem['sense']=='minimize' else target>val
    results={}
    for name,assertion in [('attainable',target==val),('strictly_better',better)]:
        s=z3.Solver();s.set(timeout=VERIFY*1000);s.add(*hard,assertion)
        query=s.to_smt2()
        results[name+'_query_sha256']=hashlib.sha256(query.encode()).hexdigest()
        t=time.monotonic();r=s.check();results[name]=str(r);results[name+'_s']=time.monotonic()-t
        if r==z3.unknown:results[name+'_reason']=s.reason_unknown()
    results['status']='verified_optimal' if results['attainable']=='sat' and results['strictly_better']=='unsat' else 'unverified'
    if results['attainable']=='unsat' or results['strictly_better']=='sat':
        results['status']='contradiction'
    return results


def inspect_invalid(row, variant, out, reason):
    """Still invoke each solver on a known malformed original input; never repair it by guessing."""
    import z3
    path=ROOT/row['path'];assert sha(path)==row['sha256']
    if variant.startswith('oms'):
        command=[str(OMS),'-optimization=true']
        if variant=='oms_maxres':command+=['-opt.maxsmt_engine=maxres','-unsat_core_generation=1']
        with (out/(variant+'.native.stdout')).open('w') as stdout,(out/(variant+'.native.stderr')).open('w') as stderr:
            run=subprocess.run(command+[str(path)],stdout=stdout,stderr=stderr)
        raw=(out/(variant+'.native.stdout')).read_text()+(out/(variant+'.native.stderr')).read_text()
        return dict(status='invalid_input',source_parse_error=reason,solver_returncode=run.returncode,
                    solver_rejected=bool(run.returncode or '(error' in raw or 'error' in raw.lower()),
                    command=command+[str(path)])
    opt=z3.Optimize();opt.set(maxsat_engine='wmax' if variant=='z3_wmax' else 'maxres')
    try:
        opt.from_file(str(path))
        return dict(status='invalid_input',source_parse_error=reason,solver_rejected=False)
    except z3.Z3Exception as error:
        return dict(status='invalid_input',source_parse_error=reason,solver_rejected=True,
                    solver_diagnostic=str(error))


def worker(args):
    import z3
    z3.set_param('parallel.enable',False)
    row=case_row(args.case)
    invalid=DATA/'manifests'/(row['suite']+'-invalid.json')
    if invalid.exists():
        rejected=json.loads(invalid.read_text()).get(row['id'])
        if rejected is not None:
            assert rejected['sha256']==row['sha256']
            return inspect_invalid(row,args.variant,Path(args.out),rejected['error'])
    problem=load_problem(row)
    if args.action=='verify':
        return verify(problem,row,args.variant,json.loads((Path(args.out)/(args.variant+'.json')).read_text()))
    if args.variant.startswith('oms'):
        return native_oms(problem,row,args.variant,Path(args.out))
    return solve_z3(problem,row,args.variant)


def limits():
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY,MEMORY))


def invoke(args,variant,action,out):
    limit=BUDGET if action=='solve' else 2*VERIFY+30
    command=[sys.executable,str(Path(__file__).resolve()),'--worker','--case',args.case,
             '--variant',variant,'--action',action,'--out',str(out)]
    stem=out/(variant+'.'+action)
    t=time.monotonic()
    with stem.with_suffix(stem.suffix+'.stdout').open('w') as stdout,stem.with_suffix(stem.suffix+'.stderr').open('w') as stderr:
        p=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=limits,
                           env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        try:
            p.wait(timeout=limit);timed_out=False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait();timed_out=True
    process=dict(returncode=p.returncode,wall_s=time.monotonic()-t,budget_s=limit,
                 command=command,status='timeout' if timed_out else 'worker_error')
    stdout=stem.with_suffix(stem.suffix+'.stdout').read_text()
    stderr=stem.with_suffix(stem.suffix+'.stderr').read_text()
    if not timed_out and p.returncode==0:
        try:
            process.update(json.loads(stdout.splitlines()[-1]))
        except ValueError:
            process['status']='output_error'
    elif not timed_out and any(x in stderr for x in ['out of memory','MemoryError','std::bad_alloc','failed to allocate']):
        process['status']='oom'
    (out/(variant+('.json' if action=='solve' else '.verify.json'))).write_text(json.dumps(process,indent=2)+'\n')
    return process


def main(args):
    expected=os.environ.get('EOS_PARAM_HARNESS_SHA256')
    if expected:
        assert sha(Path(__file__))==expected, 'Stale staged harness'
    row=case_row(args.case)
    out=Path(args.out or os.environ['EOS_RUN_DIR'])/'evidence';out.mkdir(parents=True,exist_ok=True)
    variants={'fp':['oms_fp','z3_fpkey','z3_bv'],
              'bv':['oms_bv','z3_bv'], 'bv_lia':['oms_lia','z3_lia'],
              'maxsmt':['oms_maxres','oms_omt','z3_maxres','z3_wmax']}[row['suite']]
    # Fixed reversal independent of outcomes balances first/second solver order.
    if int(row['id'][-1],16)%2:variants=list(reversed(variants))
    import z3
    provenance=dict(input=row,variants=variants,hostname=platform.node(),platform=platform.platform(),
                    python=sys.version,z3=z3.get_version_string(),z3_binary_sha256=sha(Path(z3.__file__).parent/'lib/libz3.so'),
                    oms_sha256=sha(OMS),script_sha256=sha(Path(__file__)),
                    parser_source_sha256=sha(ROOT/'scripts/revision_public_fp.py'),
                    budget_s=BUDGET,verification_query_budget_s=VERIFY,memory_bytes=MEMORY,
                    cpu=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown'),
                    fp_semantics='All ordered FP variants exclude NaN; key-based forms refine signed-zero ties.',
                    verification='SAT attainability and UNSAT strict improvement in original hard constraints; query hashes and deterministic recipe retained.')
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    results={};start=time.monotonic()
    for variant in variants:
        result=invoke(args,variant,'solve',out)
        if result['status'] in {'solver_claimed_optimal','feasible'} and 'value' in result:
            result['verification']=invoke(args,variant,'verify',out)
        results[variant]=result
        print(variant,result['status'],flush=True)
    pipeline_ok=all(r['status'] not in {'worker_error','output_error','solver_error'}
                    and r.get('verification',{}).get('status')!='contradiction' for r in results.values())
    metrics=dict(completed=True,pipeline_ok=pipeline_ok,case=row['id'],suite=row['suite'],solver_runs=len(results),
                 wall_time_s=time.monotonic()-start,results=results)
    metrics_path=Path(args.metrics or os.environ.get('EOS_METRICS_FILE',str(out.parent/'metrics.json')))
    metrics_path.write_text(json.dumps(metrics,indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--worker',action='store_true')
    ap.add_argument('--variant');ap.add_argument('--action',default='solve');ap.add_argument('--out');ap.add_argument('--metrics')
    args=ap.parse_args()
    if args.worker:
        print(json.dumps(worker(args)))
    else:
        main(args)
