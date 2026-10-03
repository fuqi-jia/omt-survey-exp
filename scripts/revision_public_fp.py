#!/usr/bin/env python3
"""Public FP, FP+BV, and bit-blasted BV diagnostic, with saved optimality checks.

Run with a Python environment containing z3-solver (4.15.4 for this revision).
The parent serializes every solver invocation. A worker does one bounded task.
Selection is fixed before solving in benchmarks/public_fp/selection.json.
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
OUT = ROOT / 'runs/rx032_public'
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


def load_problem(index):
    import z3
    row = json.loads((SOURCE/'selection.json').read_text())['selected'][index]
    path = SOURCE/row['forms']['fp']['path']; data = path.read_bytes()
    assert digest(data) == row['forms']['fp']['sha256']
    commands = list(split_commands(data.decode()))
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
        if form=='fp':
            raw=(folder/'fp.stdout').read_text()
            objectives=next(c for c in split_commands(raw) if c.startswith('(objectives'))
            inner=list(split_commands(objectives[len('(objectives'):-1]))[0]
            value=inner[1:-1].strip().split(None,1)[1]
            # Let the SMT parser interpret the exact floating-point literal.
            v=z3.FP('__rx032_value',x.sort())
            a=z3.parse_smt2_string(f'(assert (= __rx032_value {value}))',decls={'__rx032_value':v})[0]
            val=a.arg(1)
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
        return dict(status='verified' if outcomes['attainable']=='sat' and outcomes['strictly_better']=='unsat' else 'unverified',value=value,**outcomes)
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


def main():
    import z3
    OUT.mkdir(parents=True,exist_ok=True)
    selection=json.loads((SOURCE/'selection.json').read_text())
    env={'date':'2026-10-04','platform':platform.platform(),'python':sys.version,'z3':z3.get_version_string(),
         'optimathsat':subprocess.check_output([str(OMS),'-version'],text=True).strip(),
         'solver_budget_s':BUDGET,'verification_budget_s_per_query':BUDGET,'memory_bytes':MEMORY,
         'selection_sha256':digest((SOURCE/'selection.json').read_bytes()),'oms_sha256':digest(OMS.read_bytes()),
         'script_sha256':digest(Path(__file__).read_bytes()),'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown'),
         'semantics':'Native FP file unchanged. Derived key formulations exclude NaN and refine equal signed zeros by -0 < +0. Every reported optimum is rechecked in original FP constraints.'}
    (OUT/'environment.json').write_text(json.dumps(env,indent=2))
    for i,row in enumerate(selection['selected']):
        folder=OUT/f'{i:02d}';folder.mkdir(exist_ok=True)
        for form in ['fp','bvfp','bv']:
            result=folder/(form+'.solve.json')
            if result.exists():
                r=json.loads(result.read_text())
                if r.get('status')!='candidate' or (folder/(form+'.verify.json')).exists():
                    continue
            elif form=='fp':
                cmd=[str(OMS),'-optimization=true',str(SOURCE/row['forms']['fp']['path'])]
                r=invoke(cmd,BUDGET)
                (folder/'fp.stdout').write_text(r.pop('stdout'));(folder/'fp.stderr').write_text(r.pop('stderr'))
                r.update(status='candidate' if r['process_status']=='finished' and r['returncode']==0 and '(objectives' in (folder/'fp.stdout').read_text() else r['process_status'])
            else:
                if not (folder/'bv.smt2').exists():
                    prep=invoke([sys.executable,__file__,'--worker','prepare','--index',str(i),'--form',form],BUDGET+5)
                    (folder/'prepare.log').write_text(json.dumps(prep,indent=2))
                    if prep['returncode']!=0 or not (folder/'bv.smt2').exists():
                        result.write_text(json.dumps(dict(status='preparation_failed',**prep),indent=2));continue
                r=invoke([sys.executable,__file__,'--worker','solve','--index',str(i),'--form',form],BUDGET+5)
                (folder/(form+'.process.json')).write_text(json.dumps(r,indent=2))
                try:r.update(json.loads(r.pop('stdout')))
                except (ValueError,KeyError):r['status']=r['process_status'] if r['returncode']==-9 else 'error'
            result.write_text(json.dumps(r,indent=2))
            if r.get('status')=='candidate':
                v=invoke([sys.executable,__file__,'--worker','verify','--index',str(i),'--form',form],2*BUDGET+5)
                (folder/(form+'.verify.process.json')).write_text(json.dumps(v,indent=2))
                try:v=json.loads(v['stdout'])
                except (ValueError,KeyError):v['status']='verification_error'
                (folder/(form+'.verify.json')).write_text(json.dumps(v,indent=2))
            print(f'{i+1}/{len(selection["selected"])} {row["group"]} {row["sense"]} {form}: {r.get("status")}',flush=True)
    print('Completed public benchmark diagnostic.',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--worker');ap.add_argument('--index',type=int);ap.add_argument('--form');args=ap.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker,args.index,args.form)))
    else:main()
