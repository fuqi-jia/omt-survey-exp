#!/usr/bin/env python3
"""Nine predeclared nonconvex instances with provable irrational optima.

A: xy>=1, x^2+y^2>=r; minimize x+2y (two unequal local minima).
B: (x^2-a)^2+y^2<=b, y>=1; minimize x+y/10 (two components).
C: OR of two nonconvex radial/product branches with different radii.
The quartic is encoded for every backend by the same q=x^2 equality.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import time

import nra_public_20261102 as common

ROOT = common.ROOT
OUT = Path(os.environ.get("OMT_NRA_IRR_OUTPUT", ROOT / "runs/nra_irrational_20261102"))
BENCH = ROOT / "benchmarks/nra-irrational-20261102"
BASE_ASSESS, BASE_SMT, BASE_PYOMO = common.assess, common.smt_source, common.pyomo_model


def polynomial(terms, lb="-INF", ub="INF", constant="0"):
    return dict(terms=[[str(c), ids] for c, ids in terms], lb=str(lb), ub=str(ub), constant=str(constant))


def exact_formula(model):
    z3 = common.load_z3()
    family, p = model["family"], model["parameters"]
    def branch(r, reverse=False):
        s, d = z3.Sqrt(r+2), z3.Sqrt(r-2)
        x, y = (s+d)/2, (s-d)/2
        if reverse:
            x, y = y, x
        return z3.simplify(x+2*y), [z3.simplify(x), z3.simplify(y)]
    if family == "A":
        return branch(p["r"])
    if family == "B":
        q = z3.simplify(p["a"] + z3.Sqrt(p["b"]-1))
        x = z3.simplify(-z3.Sqrt(q))
        return z3.simplify(x+z3.RealVal("1/10")), [x, z3.RealVal(1), q]
    first, second = branch(p["r0"]), branch(p["r1"], True)
    return first if z3.is_true(z3.simplify(first[0] < second[0])) else second


def assess(model, x, reference):
    result = BASE_ASSESS(model, x, reference)
    if x is None or not model.get("disjunctions"):
        return result
    for branches in model["disjunctions"]:
        scores = [BASE_ASSESS(dict(model, constraints=branch), x, reference) for branch in branches]
        best = min(scores, key=lambda r: r["max_scaled_violation"])
        result["max_scaled_violation"] = max(result["max_scaled_violation"], best["max_scaled_violation"])
        result["max_absolute_violation"] = max(result["max_absolute_violation"], best["max_absolute_violation"])
    result["feasible"] = result["max_scaled_violation"] <= 1e-6
    result["reference_hit"] = result["feasible"] and result["relative_reference_error"] <= 1e-6
    return result


def generate():
    models = []
    for r in (5, 8, 13):
        models.append(dict(name=f"A_r{r}", family="A", parameters=dict(r=r),
            variables=[dict(name="x", lb="0", ub=str(r)), dict(name="y", lb="0", ub=str(r))],
            objective=polynomial([(1,[0]),(2,[1])]), sense="min",
            constraints=[polynomial([(1,[0,1])],lb=1), polynomial([(1,[0,0]),(1,[1,1])],lb=r)],
            starts=dict(I=[float(r),1.0], II=[1.0,float(r)]),
            reference_tex=rf"(3\sqrt{{{r+2}}}-\sqrt{{{r-2}}})/2"))
    for a,b in ((3,3),(4,6),(5,8)):
        models.append(dict(name=f"B_a{a}_b{b}", family="B", parameters=dict(a=a,b=b),
            variables=[dict(name="x",lb="-4",ub="4"),dict(name="y",lb="1",ub=str(math.isqrt(b)+1)),dict(name="q",lb="0",ub="16")],
            objective=polynomial([(1,[0]),("1/10",[1])]), sense="min",
            constraints=[polynomial([(1,[2]),(-1,[0,0])],lb=0,ub=0),
                         polynomial([(1,[2,2]),(-2*a,[2]),(1,[1,1])],ub=b,constant=a*a)],
            starts=dict(I=[-math.sqrt(a),1.0,float(a)],II=[math.sqrt(a),1.0,float(a)]),
            reference_tex=rf"-\sqrt{{{a}+\sqrt{{{b-1}}}}}+1/10"))
    for r0,r1 in ((5,5),(29,5),(29,8)):
        u = math.isqrt(max(r0,r1))+2
        branches = [[polynomial([(1,[0,0]),(1,[1,1])],lb=r0), polynomial([(1,[1])],ub=1)],
                    [polynomial([(1,[0,0]),(1,[1,1])],lb=r1), polynomial([(1,[0])],ub=1)]]
        value0=(3*math.sqrt(r0+2)-math.sqrt(r0-2))/2
        value1=(3*math.sqrt(r1+2)+math.sqrt(r1-2))/2
        winning=0 if value0<value1 else 1
        rr=r0 if winning==0 else r1
        models.append(dict(name=f"C_r{r0}_{r1}",family="C",parameters=dict(r0=r0,r1=r1,u=u),
            variables=[dict(name="x",lb="0",ub=str(u)),dict(name="y",lb="0",ub=str(u))],
            objective=polynomial([(1,[0]),(2,[1])]),sense="min",
            constraints=[polynomial([(1,[0,1])],lb=1)],disjunctions=[branches],
            reference_branch=winning,
            reference_tex=rf"(3\sqrt{{{rr+2}}}{'-' if winning==0 else '+'}\sqrt{{{rr-2}}})/2"))
    z3=common.load_z3()
    for m in models:
        exact, vector=exact_formula(m)
        assert z3.is_algebraic_value(exact), (m["name"],exact)
        m["reference"]=common.z3_float(exact)
        m["reference_exact_smt2"]=exact.sexpr()
        m["reference_vector"]=[common.z3_float(v) for v in vector]
        m["reference_vector_exact"]=[v.sexpr() for v in vector]
        assert assess(m,m["reference_vector"],m["reference"])["reference_hit"]
        if m["family"]=="A":
            v=m["reference_vector"]; endpoints=[v,[v[1],v[0]]]
        elif m["family"]=="B":
            a=m["parameters"]["a"];endpoints=[[-math.sqrt(a),1.0,float(a)],[math.sqrt(a),1.0,float(a)]]
        else:
            r=m["parameters"]["r0"];s,d=math.sqrt(r+2),math.sqrt(r-2)
            endpoints=[[(s+d)/2,(s-d)/2],[math.sqrt(r-1),1.0]]
        midpoint=[(a+b)/2 for a,b in zip(*endpoints)]
        assert all(assess(m,v,m["reference"])["feasible"] for v in endpoints)
        assert not assess(m,midpoint,m["reference"])["feasible"],m["name"]
        m["nonconvexity_certificate"]=dict(endpoints=endpoints,midpoint=midpoint,
            midpoint_violation=assess(m,midpoint,m["reference"])["max_scaled_violation"])
    return models


def smt_source(model,solver):
    text=BASE_SMT(model,solver)
    if model.get("disjunctions"):
        assertions=[]
        for branches in model["disjunctions"]:
            parts=[]
            for branch in branches:
                atoms=[]
                for con in branch:
                    for key,op in (("lb",">="),("ub","<=")):
                        if math.isfinite(common.number(con[key])):
                            atoms.append(f"({op} {common.smt_poly(con)} {common.smt_number(con[key])})")
                parts.append("(and "+" ".join(atoms)+")")
            assertions.append("(assert (or "+" ".join(parts)+"))")
        text=text.replace("(declare-fun obj","\n".join(assertions)+"\n(declare-fun obj")
    if solver=="z3":
        text=text.replace("(get-objectives)","(set-option :pp.decimal false)\n(get-objectives)\n(set-option :pp.decimal true)")
    return text


def pyomo_model(model,start=None):
    import pyomo.environ as p
    m=BASE_PYOMO(model,start)
    if model["family"]=="C":
        par=model["parameters"];u,r0,r1=par["u"],par["r0"],par["r1"]
        m.branch=p.Var(domain=p.Binary,initialize=0)
        m.cons.add(m.x[0]**2+m.x[1]**2 >= r0+(r1-r0)*m.branch)
        m.cons.add(m.x[1] <= 1+(u-1)*m.branch)
        m.cons.add(m.x[0] <= u-(u-1)*m.branch)
    return m


def expression_text(node):
    return node if isinstance(node,str) else "("+" ".join(expression_text(v) for v in node)+")"


def parse_exact_objective(stdout):
    z3=common.load_z3()
    z3.set_param('pp.decimal',False)
    def rewrite(match):
        polynomial,lo,hi=match.groups();v=z3.Real("isolated_value");expr=0
        for term in polynomial.replace(" ","").replace("(","").replace(")","").split("+"):
            m=re.fullmatch(r"(-?\d+)(?:\*x(?:\^(\d+))?)?",term)
            if not m:raise ValueError(term)
            c,power=m.groups();degree=int(power) if power else 1 if "x" in term else 0
            expr+=z3.RealVal(c)*v**degree
        s=z3.Solver();s.set(timeout=10000);s.add(expr==0,v>z3.RealVal(lo),v<z3.RealVal(hi))
        if s.check()!=z3.sat:raise ValueError("root isolation failed")
        return s.model().eval(v).sexpr()
    text=re.sub(r"\(_ real_algebraic_number <(.*?), \(([^,]+), ([^)]+)\)>\)",rewrite,stdout)
    for node in common.sexprs(text):
        if isinstance(node,list) and node and node[0]=="objectives":
            raw=expression_text(node[1][-1])
            if any(word in {'epsilon','oo','+oo','-oo'} for word in re.findall(r'[^\s()]+',raw)):
                return None,raw
            equality=z3.parse_smt2_string("(declare-const returned Real)(assert (= returned "+raw+"))")[0]
            value=z3.simplify(equality.arg(1))
            if not (z3.is_algebraic_value(value) or z3.is_rational_value(value)):
                raise ValueError("nonconstant objective "+raw)
            return value,raw
    return None,None


def worker(solver,name,core,start_key):
    os.sched_setaffinity(0,{core})
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    model=json.loads((OUT/'models'/(name+'.json')).read_text())
    label=solver+(('_'+start_key) if start_key else '')
    folder=OUT/label/name;folder.mkdir(parents=True,exist_ok=True)
    common.OUT=OUT;common.smt_source=smt_source;common.pyomo_model=pyomo_model;common.assess=assess
    if solver in ('z3','ocac','optimathsat','couenne') and not start_key:
        common.worker(solver,name,core)
        record=json.loads((folder/'result.json').read_text())
    else:
        start=model['starts'][start_key];x=None;status='ERROR';error=None
        if solver=='ipopt':
            import pyomo.environ as p
            from pyomo.common.tempfiles import TempfileManager
            TempfileManager.tempdir=str(folder)
            m=pyomo_model(model,start);opt=p.SolverFactory('ipopt',executable=common.SOLVERS['ipopt'])
            opt.options.update(dict(max_cpu_time=common.LIMIT,tol=1e-8,constr_viol_tol=1e-8,bound_relax_factor=0))
            t=time.monotonic()
            try:
                r=opt.solve(m,tee=False,keepfiles=True,load_solutions=False,logfile=str(folder/'solver.log'))
                status=str(r.solver.termination_condition)
                if len(r.solution):
                    m.solutions.load_from(r);x=[p.value(m.x[i]) for i in range(len(model['variables']))]
            except Exception as exc:error=repr(exc)
        else:
            from scipy.optimize import minimize
            cons=[]
            for c in model['constraints']:
                lo,hi=common.number(c['lb']),common.number(c['ub'])
                if lo==hi:cons.append(dict(type='eq',fun=lambda v,c=c,b=lo:common.evaluate(c,v)-b))
                else:
                    if math.isfinite(lo):cons.append(dict(type='ineq',fun=lambda v,c=c,b=lo:common.evaluate(c,v)-b))
                    if math.isfinite(hi):cons.append(dict(type='ineq',fun=lambda v,c=c,b=hi:b-common.evaluate(c,v)))
            bounds=[(common.number(v['lb']),common.number(v['ub'])) for v in model['variables']]
            t=time.monotonic()
            def callback(v):
                if time.monotonic()-t>common.LIMIT:raise TimeoutError('time limit')
            try:
                r=minimize(lambda v:common.evaluate(model['objective'],v),start,bounds=bounds,
                    constraints=cons,method='SLSQP',callback=callback,options=dict(ftol=1e-8,maxiter=10000))
                status='SUCCESS' if r.success else 'FAILED: '+str(r.message);x=r.x.tolist()
                (folder/'stdout.txt').write_text(str(r))
            except Exception as exc:error=repr(exc)
        record=dict(solver=solver,instance=name,start_key=start_key,start=start,status=status,
                    elapsed_s=time.monotonic()-t,timeout_s=common.LIMIT,core=core,x=x,error=error,
                    model_sha256=hashlib.sha256((OUT/'models'/(name+'.json')).read_bytes()).hexdigest(),
                    **assess(model,x,model['reference']))
    if solver in ('z3','ocac','optimathsat'):
        try:
            value,raw=parse_exact_objective((folder/'stdout.txt').read_text())
            record['reported_exact_expression']=raw
            record['reported_value']=common.z3_float(value) if value is not None else None
            expected,_=exact_formula(model);z3=common.load_z3()
            record['exact_expression_matches_reference']=value is not None and z3.is_true(z3.simplify(value==expected))
            if record.get('x') is None and value is not None and record.get('reported_objective') is None:
                t=time.monotonic();record['x']=common.recover_witness(model,common.z3_float(value))
                record['witness_check_s']=time.monotonic()-t
                record.update(assess(model,record['x'],model['reference']))
            record['optimization_hit']=record['reference_hit'] and value is not None and abs(common.z3_float(value)-model['reference'])/max(1,abs(model['reference']))<=1e-6
        except Exception as exc:
            record['exact_parse_error']=repr(exc);record['optimization_hit']=False
    else:record['optimization_hit']=record['reference_hit']
    common.save(folder/'result.json',record)
    print(label,name,record['status'],record['optimization_hit'],record.get('objective'),flush=True)


def prepare():
    for m in generate():
        common.save(OUT/'models'/(m['name']+'.json'),m);common.save(BENCH/(m['name']+'.json'),m)
    common.save(OUT/'protocol.json',dict(date='2026-11-02',families=dict(A=[5,8,13],B=[[3,3],[4,6],[5,8]],C=[[5,5],[29,5],[29,8]]),
        time_limit_s=common.LIMIT,memory_gb=4,threads=1,global_solvers=['z3','ocac','optimathsat','couenne','gurobi'],
        local_solvers=['ipopt','scipy'],local_starts=['I','II'],expected_formal_calls=69,
        selection='all nine predeclared parameter combinations; no outcome-based selection',
        references='analytic radical formulas; independent nonconvexity certificates stored with each instance',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def batch(cores):
    tasks=queue.Queue()
    for f in sorted((OUT/'models').glob('*.json')):
        m=json.loads(f.read_text())
        jobs=[(s,None) for s in ('z3','ocac','optimathsat','couenne')]
        if m['family']!='C':jobs += [(s,k) for s in ('ipopt','scipy') for k in ('I','II')]
        for s,k in jobs:
            label=s+('_'+k if k else '')
            if not (OUT/label/m['name']/'result.json').exists():tasks.put((s,m['name'],k))
    env=dict(os.environ,LD_LIBRARY_PATH='/tmp/gomt-nlp-20261102/lib',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    def group(core):
        while True:
            try:s,name,k=tasks.get_nowait()
            except queue.Empty:return
            folder=OUT/(s+('_'+k if k else ''))/name;folder.mkdir(parents=True,exist_ok=True)
            cmd=[sys.executable,str(Path(__file__).resolve()),'--worker',s,name,'--core',str(core)]
            if k:cmd+=['--start',k]
            p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
            t=time.monotonic()
            try:
                stdout,stderr=p.communicate(timeout=2 * common.LIMIT + 80)
                (folder/'worker.stdout').write_text(stdout);(folder/'worker.stderr').write_text(stderr)
                if not (folder/'result.json').exists():
                    common.save(folder/'result.json',dict(solver=s,instance=name,start_key=k,status='WORKER_ERROR',elapsed_s=time.monotonic()-t,x=None,feasible=False,reference_hit=False,optimization_hit=False))
                print(stdout.strip()[-190:] or f'{s} {name} WORKER_ERROR',flush=True)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.communicate()
                common.save(folder/'result.json',dict(solver=s,instance=name,start_key=k,status='TIMEOUT',elapsed_s=time.monotonic()-t,x=None,feasible=False,reference_hit=False,optimization_hit=False))
    with ThreadPoolExecutor(len(cores)) as pool:list(pool.map(group,cores))


def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true')
    p.add_argument('--worker',nargs=2);p.add_argument('--start');p.add_argument('--core',type=int);p.add_argument('--cores',type=int,nargs='+',default=[0,2,4,6,8,10])
    a=p.parse_args()
    if a.prepare:prepare()
    if a.worker:worker(*a.worker,a.core,a.start)
    if a.run:batch(a.cores)


if __name__=='__main__':main()
