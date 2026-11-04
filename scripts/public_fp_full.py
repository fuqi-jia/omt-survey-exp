#!/usr/bin/env python3
"""Public FP, FP+BV, and bit-blasted BV diagnostic, with saved optimality checks.

Run with Z3 5.3.2 and OptiMathSAT 1.7.4 over the complete 1120-instance suite.
The parent schedules isolated single-core cases; a worker does one bounded task.
The complete input manifest is benchmarks/public_fp/selection-full.json.
"""
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
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'benchmarks/public_fp'
OUT = ROOT / 'runs/public_fp_full_20261028'
OMS = ROOT / 'tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat'
BUDGET = 30
MEMORY = 4 * 1024**3


def digest(data):
    return hashlib.sha256(data).hexdigest()


def split_commands(s):
    """Top-level SMT-LIB forms, respecting comments, quoted symbols and strings."""
    depth = 0; start = None; quote = None; comment = False; i = 0
    while i < len(s):
        c = s[i]
        if comment:
            if c == '\n': comment = False
        elif quote:
            if c == quote:
                if quote == '"' and i+1 < len(s) and s[i+1] == '"': i += 1
                else: quote = None
        elif c == ';': comment = True
        elif c in '|"': quote = c
        elif c == '(':
            if depth == 0: start = i
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: yield s[start:i+1]
            if depth < 0: raise ValueError('Unbalanced SMT-LIB input')
        i += 1
    if depth or quote: raise ValueError('Incomplete SMT-LIB input')


def normalize_quoted_symbols(source):
    """Bijectively rename legacy quoted names containing a backslash.

    ESBMC's published inputs contain such identifiers. Modern SMT-LIB parsers
    reject them. This changes only symbol names, never constants or formulas;
    ordinary identifiers and already conforming quoted names remain unchanged.
    """
    if '\\' not in source:
        return source
    prefix = '__fp_legacy_' + digest(source.encode())[:16] + '_'
    while prefix in source:
        prefix += 'x'
    result = []
    names = {}
    i = 0
    while i < len(source):
        c = source[i]
        if c == ';':
            end = source.find('\n', i)
            end = len(source) if end < 0 else end
        elif c == '"':
            end = i + 1
            while end < len(source):
                if source[end] == '"':
                    end += 1
                    if end >= len(source) or source[end] != '"':
                        break
                end += 1
        elif c == '|':
            end = source.index('|', i + 1) + 1
            token = source[i:end]
            if '\\' in token:
                if token not in names:
                    names[token] = prefix + str(len(names))
                result.append(names[token])
                i = end
                continue
        else:
            end = i + 1
        result.append(source[i:end])
        i = end
    return ''.join(result)


def load_problem(index):
    import z3
    row = json.loads((SOURCE/'selection-full.json').read_text())['selected'][index]
    path = SOURCE/row['forms']['fp']['path']; data = path.read_bytes()
    assert digest(data) == row['forms']['fp']['sha256']
    commands = list(split_commands(normalize_quoted_symbols(data.decode())))
    objective = next(c for c in commands if c.startswith(('(minimize ', '(maximize ')))
    sense, name = re.fullmatch(r'\((minimize|maximize)\s+(\S+)\)', objective).groups()
    base = '\n'.join(c for c in commands if not c.startswith(('(minimize','(maximize','(check-sat','(get-','(exit','(set-logic','(set-info','(set-option')))
    # Resolve the actual declared sort through the SMT-LIB parser, including
    # Float32/Float64 aliases and arbitrary whitespace in sort declarations.
    parsed = list(z3.parse_smt2_string(base + f'\n(assert (= {name} {name}))'))
    x = parsed[-1].arg(0)
    assert z3.is_fp(x)
    eb, sb = x.sort().ebits(), x.sort().sbits()
    assertions = parsed[:-1]
    bits = z3.fpToIEEEBV(x); width = eb+sb
    key_expr = z3.If(z3.Extract(width-1,width-1,bits) == 1, ~bits, bits ^ z3.BitVecVal(1 << (width-1),width))
    key = z3.BitVec('__rx032_key',width)
    return row, path, sense, x, key, key_expr, assertions


def worker(task,index,form):
    import z3
    z3.set_param('parallel.enable',False)
    row, path, sense, x, key, expr, assertions = load_problem(index)
    folder=OUT/f'{index:02d}';folder.mkdir(parents=True,exist_ok=True)
    if task=='prepare':
        s=z3.Solver();s.add(*assertions,z3.Not(z3.fpIsNaN(x)),key==expr)
        (folder/'bvfp.smt2').write_text(s.to_smt2())
        if form == 'bvfp':
            return {'status':'prepared','input_bytes':(folder/'bvfp.smt2').stat().st_size}
        g=z3.Goal();g.add(*s.assertions())
        t0=time.monotonic();gs=z3.Then('simplify','fpa2bv','simplify')(g)
        assert len(gs)==1
        pure=z3.Solver();pure.add(*gs[0]);txt=pure.to_smt2()
        assert 'FloatingPoint' not in txt and 'fp.' not in txt
        (folder/'bv.smt2').write_text(txt)
        return {'status':'prepared','translation_s':time.monotonic()-t0,'input_bytes':len(txt)}
    if task=='solve':
        s=z3.Optimize();s.set(timeout=BUDGET*1000);s.from_file(str(folder/(form+'.smt2')))
        h=s.minimize(key) if sense=='minimize' else s.maximize(key)
        t0=time.monotonic();r=s.check();elapsed=time.monotonic()-t0
        if r!=z3.sat:return {'status':str(r),'reason':s.reason_unknown(),'solve_s':elapsed}
        value=s.model().eval(key,model_completion=True)
        # Check a complete bound, not merely Optimize's SAT result.
        lo=str(h.lower());hi=str(h.upper())
        proved=lo==hi and value.as_long()==int(lo)
        return {'status':'candidate' if proved else 'feasible','key':value.as_long(),
                'lower':lo,'upper':hi,'solve_s':elapsed}
    if task=='verify':
        record=json.loads((folder/(form+'.solve.json')).read_text())
        is_nan = False
        if form=='fp':
            raw=(folder/'fp.stdout').read_text()
            objectives=next(c for c in split_commands(raw) if c.startswith('(objectives'))
            inner=list(split_commands(objectives[len('(objectives'):-1]))[0]
            value=inner[1:-1].strip().split(None,1)[1]
            # Let the SMT parser interpret the exact floating-point literal.
            v=z3.FP('__rx032_value',x.sort())
            a=z3.parse_smt2_string(f'(assert (= __rx032_value {value}))',decls={'__rx032_value':v})[0]
            val=a.arg(1)
            is_nan=z3.is_true(z3.simplify(z3.fpIsNaN(val)))
            equal=x==val;better=z3.fpLT(x,val) if sense=='minimize' else z3.fpGT(x,val)
        else:
            k=z3.BitVecVal(record['key'],key.size());equal=z3.And(z3.Not(z3.fpIsNaN(x)),expr==k)
            better=z3.And(z3.Not(z3.fpIsNaN(x)),z3.ULT(expr,k) if sense=='minimize' else z3.UGT(expr,k))
            value=str(record['key'])
        outcomes={}
        for label,extra in [('attainable',equal),('strictly_better',better)]:
            s=z3.Solver();s.set(timeout=BUDGET*1000);s.add(*assertions,extra)
            (folder/(form+'.'+label+'.smt2')).write_text(s.to_smt2())
            t0=time.monotonic();r=s.check();outcomes[label]=str(r);outcomes[label+'_s']=time.monotonic()-t0
            if r==z3.unknown:outcomes[label+'_reason']=s.reason_unknown()
        confirmed=outcomes['attainable']=='sat' and outcomes['strictly_better']=='unsat'
        return dict(status=('nan' if is_nan else 'verified') if confirmed else 'unverified',value=value,**outcomes)
    raise ValueError(task)


def limits():
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY,MEMORY))


def invoke(cmd,timeout):
    t0=time.monotonic()
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        start_new_session=True,preexec_fn=limits,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
    try:
        stdout,stderr=p.communicate(timeout=timeout);status='finished'
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate();status='timeout'
    return dict(process_status=status,returncode=p.returncode,wall_s=time.monotonic()-t0,stdout=stdout,stderr=stderr)


def parse_worker(record):
    try:
        return json.loads(record.get('stdout',''))
    except (ValueError,TypeError):
        return None


def failure_kind(record):
    text=(record.get('stdout','')+' '+record.get('stderr','')).lower()
    if any(x in text for x in ['out of memory','out_of_memory','bad_alloc','memoryerror','cannot allocate memory']):
        return 'out_of_memory'
    if record.get('process_status')=='timeout':
        return 'timeout'
    return 'error'


def run_case(index):
    selection=json.loads((SOURCE/'selection-full.json').read_text())['selected']
    row=selection[index]
    folder=OUT/f'{index:02d}'
    folder.mkdir(parents=True,exist_ok=True)
    result={'index':index,'group':row['group'],'sense':row['sense'],'upstream':row['upstream'],'routes':{}}
    for form in ['fp','bvfp','bv']:
        final=folder/(form+'.final.json')
        if final.exists():
            result['routes'][form]=json.loads(final.read_text())
            continue
        rec={'form':form,'status':None}
        if form=='fp':
            proc=invoke([str(OMS),'-optimization=true',str(SOURCE/row['forms']['fp']['path'])],BUDGET)
            (folder/'fp.stdout').write_text(proc['stdout'])
            (folder/'fp.stderr').write_text(proc['stderr'])
            token=re.search(r'(?m)^\s*(sat|unsat|unknown)\s*$',proc['stdout'])
            status=token.group(1) if token else None
            finished=proc['process_status']=='finished' and proc['returncode']==0
            candidate=finished and status=='sat' and '(objectives' in proc['stdout']
            solve=dict(proc,status='candidate' if candidate else status if finished and status in ['unsat','unknown'] else failure_kind(proc))
        else:
            if not (folder/(form+'.smt2')).exists():
                prep=invoke([sys.executable,__file__,'--worker','prepare','--index',str(index),'--form',form],BUDGET+5)
                (folder/(form+'.prepare.json')).write_text(json.dumps(prep,indent=2))
                if prep['returncode']!=0 or not (folder/(form+'.smt2')).exists():
                    rec.update(status=failure_kind(prep),stage='prepare')
                    final.write_text(json.dumps(rec,indent=2))
                    result['routes'][form]=rec
                    continue
            proc=invoke([sys.executable,__file__,'--worker','solve','--index',str(index),'--form',form],BUDGET+5)
            solve=parse_worker(proc)
            if solve is None:
                solve=dict(proc,status=failure_kind(proc))
            elif solve.get('status')=='unknown':
                solve['status']='timeout' if 'timeout' in solve.get('reason','').lower() or solve.get('solve_s',0)>=BUDGET*.95 else 'unknown'
            (folder/(form+'.process.json')).write_text(json.dumps(proc,indent=2))
        (folder/(form+'.solve.json')).write_text(json.dumps(solve,indent=2))
        if solve.get('status')=='candidate':
            proc=invoke([sys.executable,__file__,'--worker','verify','--index',str(index),'--form',form],2*BUDGET+5)
            verify=parse_worker(proc)
            (folder/(form+'.verify.process.json')).write_text(json.dumps(proc,indent=2))
            if verify is None:
                verify={'status':'unverified','reason':failure_kind(proc)}
            (folder/(form+'.verify.json')).write_text(json.dumps(verify,indent=2))
            rec.update(status=verify['status'] if verify.get('status') in ['verified','nan'] else 'unverified_candidate',verification=verify)
        elif solve.get('status')=='feasible':
            rec.update(status='unverified_candidate')
        else:
            rec.update(status=solve.get('status','error'),stage='solve')
        rec['solve_s']=solve.get('solve_s',solve.get('wall_s'))
        final.write_text(json.dumps(rec,indent=2))
        result['routes'][form]=rec
    casepath=OUT/'cases'/f'{index:04d}.json'
    casepath.parent.mkdir(exist_ok=True)
    temporary=casepath.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,indent=2))
    temporary.replace(casepath)
    return result


def case_process(index):
    available=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{available[index%len(available)]})
    try:
        return run_case(index)
    except Exception as ex:
        import traceback
        rec={'index':index,'infrastructure_error':str(ex),'traceback':traceback.format_exc()}
        p=OUT/'cases'/f'{index:04d}.error.json';p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(rec,indent=2))
        return rec


def summarize():
    import collections
    rows=[json.loads(p.read_text()) for p in sorted((OUT/'cases').glob('[0-9][0-9][0-9][0-9].json'))]
    counts={f:collections.Counter() for f in ['fp','bvfp','bv']}
    groups={}
    for r in rows:
        g=groups.setdefault(r['group'],{'instances':0,**{f:0 for f in counts}});g['instances']+=1
        for f,x in r['routes'].items():
            counts[f][x['status']]+=1
            if x['status']=='verified':g[f]+=1
    report={'population':1120,'completed_instances':len(rows),'groups':groups,'route_status_counts':{f:dict(c) for f,c in counts.items()}}
    tmp=OUT/'summary.tmp';tmp.write_text(json.dumps(report,indent=2));tmp.replace(OUT/'summary.json')
    return report


def main(args):
    import z3,concurrent.futures,multiprocessing
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'cases').mkdir(exist_ok=True)
    selection=json.loads((SOURCE/'selection-full.json').read_text())
    assert selection['population']==len(selection['selected'])==1120
    env={'date':'2026-10-28','hostname':platform.node(),'platform':platform.platform(),'python':sys.version,
         'z3':z3.get_version_string(),'optimathsat':subprocess.check_output([str(OMS),'-version'],text=True).strip(),
         'solver_budget_s':BUDGET,'verification_budget_s_per_query':BUDGET,'memory_bytes':MEMORY,'workers':args.workers,
         'selection_sha256':digest((SOURCE/'selection-full.json').read_bytes()),'oms_sha256':digest(OMS.read_bytes()),
         'script_sha256':digest(Path(__file__).read_bytes()),'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown')}
    path=OUT/'environment.json'
    if path.exists():
        old=json.loads(path.read_text())
        for key in ['z3','optimathsat','selection_sha256','oms_sha256','script_sha256']:
            assert old[key]==env[key],('Resume environment mismatch',key)
    path.write_text(json.dumps(env,indent=2))
    ids=list(range(1120)) if not args.indices else [int(x) for x in args.indices.split(',')]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn')) as pool:
        fs={pool.submit(case_process,i):i for i in ids}
        for fut in concurrent.futures.as_completed(fs):
            r=fut.result();report=summarize()
            print(json.dumps({'case':fs[fut],'completed':report['completed_instances'],'error':r.get('infrastructure_error'),'status':{f:x['status'] for f,x in r.get('routes',{}).items()}},sort_keys=True),flush=True)
    print(json.dumps(summarize(),indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--worker');ap.add_argument('--index',type=int);ap.add_argument('--form');ap.add_argument('--workers',type=int,default=16);ap.add_argument('--indices');args=ap.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker,args.index,args.form)))
    else:
        main(args)
