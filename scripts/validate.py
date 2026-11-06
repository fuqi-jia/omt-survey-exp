#!/usr/bin/env python3
"""Validate retained bytes, complete call matrices, inputs and paper statistics.

No optimizer is rerun. --deep additionally rechecks NRA candidates/references
and the archived FP verification protocol using the original audit code.
"""
from pathlib import Path
from collections import Counter, defaultdict
import argparse, csv, gzip, hashlib, io, json, math, re, statistics
import subprocess, sys, tarfile, tempfile, os

ROOT = Path(__file__).resolve().parents[1]
BASE = 'runs/uniform600_20261106'

def digest(data): return hashlib.sha256(data).hexdigest()
def csv_rows(path):
    with (ROOT/path).open(newline='', encoding='utf-8') as f:return list(csv.DictReader(f))
def mapping():
    with gzip.open(ROOT/'provenance/paths.csv.gz','rt',encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def flag(s): return s in ['True','true']
def load_members(path, suffix=None):
    with tarfile.open(ROOT/path) as t:
        return {m.name:t.extractfile(m).read() for m in t if m.isfile() and (suffix is None or m.name.endswith(suffix))}
def load_json_members(path):return {n:json.loads(v) for n,v in load_members(path,'.json').items()}
def materialize(destination):
    """Restore retained originals to their execution paths, outside this repo."""
    groups=defaultdict(list)
    for e in mapping():groups[e['path']].append(e)
    for path, entries in groups.items():
        if all(not e['member'] for e in entries):
            contents=(ROOT/path).read_bytes()
            for e in entries:
                p=destination/e['old_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(contents)
        else:
            by_member=defaultdict(list)
            for e in entries:by_member[e['member']].append(e)
            with tarfile.open(ROOT/path) as t:
                for m in t:
                    if m.name not in by_member:continue
                    contents=t.extractfile(m).read()
                    for e in by_member[m.name]:
                        p=destination/e['old_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(contents)

def byte_checks():
    groups=defaultdict(dict); original_paths=set()
    for e in mapping():
        assert e['old_path'] not in original_paths,e['old_path']
        original_paths.add(e['old_path'])
        key=e['member']; old=groups[e['path']].get(key)
        assert old is None or old==e['sha256']
        groups[e['path']][key]=e['sha256']
    count=0
    for path, expected in groups.items():
        p=ROOT/path;assert p.is_file(),path
        if '' in expected:
            assert len(expected)==1
            assert digest(p.read_bytes())==expected[''];count+=1
        else:
            found=set()
            with tarfile.open(p) as t:
                for member in t:
                    assert member.isfile() and member.name not in found,(path,member.name)
                    assert member.name in expected,(path,member.name)
                    assert digest(t.extractfile(member).read())==expected[member.name],(path,member.name)
                    found.add(member.name);count+=1
            assert found==set(expected),path
    return dict(original_paths=len(original_paths),unique_preserved_objects=count,passed=True)

def input_checks():
    # All 97 actual parameterized models and their SMT/MiniZinc encodings.
    perf=json.loads((ROOT/'benchmarks/performance/manifest.json').read_text())
    inputs=load_members('benchmarks/performance/inputs.tar.gz')
    assert len(perf['instances'])==97 and len(inputs)==291
    for instance in perf['instances']:
        for spec in instance['inputs'].values():assert digest(inputs[spec['path']])==spec['sha256']
        assert instance['name']+'.json' in inputs
    # All released CGM inputs in the selected groups, original and actual adapters.
    manifest=json.loads((ROOT/'benchmarks/maxsmt/manifest.json').read_text())
    assert len(manifest['instances'])==1199 and len(manifest['excluded'])==1
    hashes={}
    with tarfile.open(ROOT/'benchmarks/maxsmt/inputs.tar.gz') as t:
        for m in t:
            assert m.isfile() and m.name not in hashes
            hashes[m.name]=digest(t.extractfile(m).read())
    assert len(hashes)==7194
    for instance in manifest['instances']:assert hashes[instance['id']+'/original.smt2']==instance['source_sha256']
    for row in csv_rows('results/maxsmt/results.csv'):
        assert hashes[row['instance']+'/'+row['config']+'.smt2']==row['input_sha256']
    excluded=(ROOT/'benchmarks/maxsmt/excluded/original.smt2').read_bytes()
    assert digest(excluded)==manifest['excluded'][0]['source_sha256']
    # Complete FP source cohort, not a sample of its 1120 cases.
    selection=json.loads((ROOT/'benchmarks/floating-point/selection.json').read_text())['selected']
    fp=load_members('benchmarks/floating-point/inputs.tar.gz')
    assert len(selection)==1120
    for s in selection:assert digest(fp[s['forms']['fp']['path']])==s['forms']['fp']['sha256']
    assert len(fp)==1120
    return dict(performance_instances=97,cgm_instances=1199,cgm_input_files=7194,fp_instances=1120,passed=True)

def clean_tex(s):
    s=s.replace('\\texttt{OPT}','OPT').replace('\\,','').replace('$','').replace('\\ne','≠')
    return re.sub(r'\s+',' ',s).strip()
def tex_rows(name):
    text=(ROOT/'paper/tables'/name).read_text()
    return [[clean_tex(c) for c in line.rsplit('\\\\',1)[0].split('&')]
            for line in text.splitlines() if '&' in line and line.rstrip().endswith('\\\\')]

def timing_cell(rows, completion='proved_optimal', elapsed='runtime_s'):
    times=[float(r[elapsed]) if flag(r[completion]) else float('inf') for r in rows]
    val=statistics.median(times);n=sum(flag(r[completion]) for r in rows);total=len(rows)
    if math.isinf(val):
        statuses={r['status'] for r in rows}
        memory=sum('memory' in r.get('error_message','').lower() or 'bad_alloc' in r.get('error_message','').lower() for r in rows)
        if memory>total/2:text='MO'
        elif any(r.get('solver')=='gecode' and r['status'] in ['SAT','FEASIBLE'] for r in rows):text='feas.'
        else:text='T/O'
    else:text='<0.01' if val<0.01 else f'{val:.2f}'
    if n!=total and (math.isfinite(val) or n or text=='T/O' and total==10):text+=f' ({n}/{total})'
    return text

def table_checks():
    reports={}
    perf=csv_rows('results/performance/results.csv')
    assert len(perf)==993 and len({(r['name'],r['solver']) for r in perf})==993
    raw=load_json_members('results/performance/records.tar.gz')
    for r in perf:
        if r['timeout_s']:assert float(r['timeout_s'])==600
        else:
            command=raw['cells/'+r['name']+'__'+r['solver']+'.json']['command']
            assert command[command.index('--timeout')+1]=='600'
    for row in perf:
        r=raw['cells/'+row['name']+'__'+row['solver']+'.json']
        for k in ['status','proved_optimal','runtime_s','objective']:
            a,b=row[k],r.get(k)
            if k=='runtime_s':assert float(a)==b
            elif k=='proved_optimal':assert flag(a)==b
            elif k=='objective':assert (a=='' and b is None) or float(a)==b
            else:assert a==b
    for key in {r['name'] for r in perf}:
        objectives={r['objective'] for r in perf if r['name']==key and flag(r['proved_optimal'])}
        assert len(objectives)==1,(key,objectives)
    solvers=['z3','optimathsat','cbc','highs','scip','gurobi','cplex','gecode','cpsat']
    family_names={'GAP':'gap','配置':'config','背包':'knapsack','集合覆盖':'setcover'}
    linear=[r for r in tex_rows('05-linear.tex') if any(r[0].startswith(f) for f in family_names)]
    assert len(linear)==19
    linear_export=[]
    for row in linear:
        m=re.fullmatch(r'(GAP|配置|背包|集合覆盖)(\d+)',row[0]);assert m,row[0]
        f,n=family_names[m[1]],int(m[2])
        for solver,cell in zip(solvers,row[1:]):
            calls=[r for r in perf if r['family']==f and int(r['size'])==n and r['solver']==solver]
            assert len(calls)==3
            wanted=timing_cell(calls)
            # Existing table suppresses 0/3 for unsolved linear groups.
            assert clean_tex(cell)==wanted,(row[0],solver,cell,wanted)
            linear_export.append(dict(family=f,size=n,solver=solver,calls=3,proved_optimal=sum(flag(r['proved_optimal']) for r in calls),display=cell))
    write_csv('paper/tables/05-linear.csv',linear_export)
    job_solvers=['z3','optimathsat','cbc-bigm','highs-bigm','scip-bigm','gurobi-bigm','gurobi-ind','cplex-bigm','cplex-ind','gecode','cpsat']
    job_rows=[r for r in tex_rows('06-jobshop.tex') if r[0] in ['7','8','9','10']]
    assert len(job_rows)==4
    job_export=[]
    for row in job_rows:
        for solver,cell in zip(job_solvers,row[1:]):
            calls=[r for r in perf if r['family']=='jobshop' and r['size']==row[0] and r['solver']==solver]
            assert len(calls)==10
            wanted=timing_cell(calls)
            assert cell==wanted,(row[0],solver,cell,wanted)
            job_export.append(dict(size=row[0],solver=solver,calls=10,proved_optimal=sum(flag(r['proved_optimal']) for r in calls),display=cell,total_runtime_s=math.fsum(float(r['runtime_s']) for r in calls)))
    write_csv('paper/tables/06-jobshop.csv',job_export)
    plot=csv_rows('paper/figures/05-jobshop-cumulative/data.csv');assert len(plot)==44
    for r in plot:
        match=next(x for x in job_export if str(x['size'])==r['size'] and x['solver']==r['solver'])
        assert math.isclose(float(r['total_runtime_s']),match['total_runtime_s'],rel_tol=1e-14)
        assert int(r['proved_optimal'])==match['proved_optimal']
    hull=[r for r in perf if r['solver']=='highs-hull' and r['size']=='8']
    assert len(hull)==10 and timing_cell(hull)=='229.53 (9/10)'
    reports['performance']=dict(calls=993,linear_cells=171,jobshop_cells=44,figure_points=44,passed=True)

    exact=csv_rows('results/large-coefficients/results.csv');assert len(exact)==360
    order=['z3','optimathsat','cpsat','cbc','highs','scip','cplex','gurobi','scip-exact']
    printed=[r for r in tex_rows('07-large-coefficients.tex') if r[0] in ['OMT','CP','MILP']]
    assert len(printed)==9
    export=[]
    for row,solver in zip(printed,order):
        for cell,e in zip(row[2:],[40,54,60,200]):
            calls=[r for r in exact if r['solver']==solver and int(r['exponent'])==e]
            assert len(calls)==10
            good=sum(flag(r['correct']) for r in calls)
            assert cell==f'{good}/10',(solver,e,cell,good)
            export.append(dict(solver=solver,exponent=e,correct=good,total=10))
    write_csv('paper/tables/07-large-coefficients.csv',export)
    hilbert=csv_rows('results/hilbert/results.csv');assert len(hilbert)==42
    printed=[r for r in tex_rows('08-hilbert.tex') if r[0] in ['OMT','MILP']]
    status={'correct':'正确','wrong':'≠精确解','infeasible':'判不可行'}
    export=[]
    for row,solver in zip(printed,['z3','optimathsat','cbc','highs','scip','gurobi','cplex']):
        for cell,n in zip(row[2:],[6,8,10,12,14,16]):
            record=next(r for r in hilbert if r['solver']==solver and int(r['n'])==n)
            assert cell==status[record['status']],(solver,n,cell,record['status'])
            export.append(dict(solver=solver,n=n,status=record['status'],display=cell))
    write_csv('paper/tables/08-hilbert.csv',export)
    reports['numerical']=dict(large_coefficient_calls=360,hilbert_calls=42,passed=True)

    public=csv_rows('results/nonlinear/public/results.csv');disj=csv_rows('results/nonlinear/disjunctive/results.csv')
    irrational=csv_rows('results/nonlinear/irrational/results.csv');single=csv_rows('results/nonlinear/single-variable/results.csv')
    assert [len(x) for x in [public,disj,irrational,single]]==[301,45,69,46]
    for group,n in [('public',43),('disjunctive',9),('irrational',9)]:
        rows={'public':public,'disjunctive':disj,'irrational':irrational}[group]
        models=load_json_members('benchmarks/nonlinear/'+group+'/models.tar.gz')
        assert len(models)==n
        raw=load_json_members('results/nonlinear/'+group+'/records.tar.gz')
        for row in rows:
            r=raw[row['configuration']+'/'+row['instance']+'/result.json']
            for key in ['status','feasible','reference_hit']:
                assert row[key]==str(r[key]),(group,row['instance'],key)
            if r.get('model_sha256'):
                content=load_members('benchmarks/nonlinear/'+group+'/models.tar.gz')[row['instance']+'.json']
                assert r['model_sha256']==digest(content)
            assert r['timeout_s']==600
    names=['z3','ocac','optimathsat','scipy','ipopt','gurobi','couenne']
    pmodels=load_json_members('benchmarks/nonlinear/public/models.tar.gz')
    dmodels=load_json_members('benchmarks/nonlinear/disjunctive/models.tar.gz')
    printed=[r for r in tex_rows('10-nra-multi.tex') if r[0] in ['Z3','OCAC','OptiMathSAT','SLSQP','IPOPT','Gurobi','Couenne'] and len(r)==10]
    assert len(printed)==7
    export=[]
    for row,solver in zip(printed,names):
        p=[sum(flag(r['reference_hit']) for r in public if r['solver']==solver and len(pmodels[r['instance']+'.json']['variables'])==n) for n in [2,3,4,5]]
        d=[sum(flag(r['reference_hit']) for r in disj if r['solver']==solver and dmodels[r['instance']+'.json']['n']==n) for n in [4,8,12]] if solver not in ['scipy','ipopt'] else None
        values=p+[sum(p)]+(d+[sum(d)] if d else ['--']*4)
        assert row[1:]==list(map(str,values)),(solver,row[1:],values)
        export.append(dict(solver=solver,public_2=p[0],public_3=p[1],public_4=p[2],public_5=p[3],public_total=sum(p),disjunctive_4=d[0] if d else '',disjunctive_8=d[1] if d else '',disjunctive_12=d[2] if d else '',disjunctive_total=sum(d) if d else ''))
    write_csv('paper/tables/10a-nra-multi.csv',export)
    imodels=load_json_members('benchmarks/nonlinear/irrational/models.tar.gz')
    printed=[r for r in tex_rows('10-nra-multi.tex') if len(r)==7 and re.match(r'\\mathrm\{[ABC]\}',r[0])]
    assert len(printed)==9
    inames=['A_r5','A_r8','A_r13','B_a3_b3','B_a4_b6','B_a5_b8','C_r5_5','C_r29_5','C_r29_8']
    export=[]
    for row,name in zip(printed,inames):
        assert row[1]==f'{imodels[name+".json"]["reference"]:.8f}'
        for solver,cell in zip(['z3','ocac','optimathsat','gurobi','couenne'],row[2:]):
            r=next(r for r in irrational if r['instance']==name and r['configuration']==solver)
            if r['status']=='TIMEOUT':value='超时'
            elif solver=='couenne' and r['status']=='infeasible':value='报不可行'
            elif solver=='optimathsat' and name=='A_r5':value=r'3+\varepsilon (OPT)'
            else:value=f'{float(r["reported_value"] if solver in ["z3","ocac","optimathsat"] else r["objective"]):.8f}'
            assert cell==value,(name,solver,cell,value)
            export.append(dict(instance=name,solver=solver,reference=f'{imodels[name+".json"]["reference"]:.8f}',display=cell,status=r['status']))
    write_csv('paper/tables/10b-nra-irrational.csv',export)
    # Table 9 values are joined to the 46 original records, including both starts.
    rows=[r for r in tex_rows('09-nra-single.tex') if r[0].startswith('\\max') or r[0].startswith('\\min')]
    assert len(rows)==6
    single_export=[]
    cases=['A_sqrt2','A_sqrt5','B_5_9','B_9_25','C1_inf_unattained','C2_unbounded_below']
    for row,case in zip(rows,cases):
        for solver,cell in zip(['z3','ocac','optimathsat','scipy','ipopt','gurobi','couenne'],row[2:]):
            matching=[r for r in single if r['case']==case and r['solver']==solver]
            assert len(matching)==(2 if solver in ['scipy','ipopt'] and case in ['B_5_9','B_9_25'] else 1)
            single_export.append(dict(case=case,solver=solver,display=cell,source_records=json.dumps([r['record'] for r in matching],ensure_ascii=False)))
    write_csv('paper/tables/09-nra-single.csv',single_export)
    api=load_json_members('results/nonlinear/optimathsat-api/records.tar.gz')
    api_rows=[]
    for name in ['A_r5','C1_inf_unattained']:
        r=api['optimathsat/'+name+'.json']
        assert r['timeout_s']==600 and r['objective_status']=='SAT_OPTIMAL' and r['objective_status_code']==3
        group,member=('irrational','optimathsat/A_r5/input.smt2') if name=='A_r5' else ('single-variable','nra_base/optimathsat/C1_inf_unattained.smt2')
        assert digest(load_members('results/nonlinear/'+group+'/records.tar.gz')[member])==r['original_cli_sha256']
        api_rows.append(dict(case=name,status=r['objective_status'],status_code=r['objective_status_code'],
                             reported_optimum=r['values']['optimum']['term'],reference=r['independent_reference']['exact'],
                             model=json.dumps(r['model'],ensure_ascii=False),elapsed_s=r['elapsed_s'],timeout_s=r['timeout_s'],
                             record='results/nonlinear/optimathsat-api/records.tar.gz#optimathsat/'+name+'.json'))
    write_csv('results/nonlinear/optimathsat-api/results.csv',api_rows)
    reports['nonlinear']=dict(single_calls=46,public_calls=301,disjunctive_calls=45,irrational_calls=69,passed=True)

    maxsmt=csv_rows('results/maxsmt/results.csv');assert len(maxsmt)==4796
    raw=load_json_members('results/maxsmt/records.tar.gz')
    assert len({(r['instance'],r['config']) for r in maxsmt})==4796
    statuses=Counter(r['status'] for r in maxsmt);assert statuses==Counter(optimal=4159,unsat=164,timeout=473),statuses
    for row in maxsmt:
        r=raw[row['instance']+'/'+row['config']+'/result.json']
        assert row['status']==r['status'] and float(row['elapsed_s'])==r['elapsed_s']
        assert r['timeout_s']==600
        if r['status']=='optimal':
            assert r['validation']['feasible'] and r['validation']['recomputed_costs']==r['objective']
        assert flag(row['completed'])==(r['status'] in ['optimal','unsat'])
    for instance in {r['instance'] for r in maxsmt}:
        group=[r for r in maxsmt if r['instance']==instance and flag(r['completed'])]
        assert len({r['objective'] for r in group if r['status']=='optimal'})<=1
        assert len({r['status'] for r in group})<=1
    printed=[r for r in tex_rows('11-maxsmt.tex') if len(r)==7 and r[0] in ['2','11','21']]
    assert len(printed)==9;export=[]
    for row in printed:
        for solver,cell in zip(['z3-maxres','z3-wmax','oms-omt','oms-maxres'],row[3:]):
            calls=[r for r in maxsmt if r['N']==row[0] and r['p']==row[1] and r['config']==solver]
            assert len(calls)==int(row[2]);wanted=timing_cell(calls,'completed','elapsed_s')
            assert cell==wanted,(row[:3],solver,cell,wanted)
            export.append(dict(N=row[0],p=row[1],config=solver,total=len(calls),optimal=sum(r['status']=='optimal' for r in calls),hard_unsat=sum(r['status']=='unsat' for r in calls),unfinished=sum(not flag(r['completed']) for r in calls),display=cell))
    write_csv('paper/tables/11-maxsmt.csv',export)
    reports['maxsmt']=dict(calls=4796,statuses=dict(statuses),passed=True)

    fp=csv_rows('results/floating-point/results.csv');assert len(fp)==3360
    raw=load_json_members('results/floating-point/records.tar.gz')
    groups=['griggio','heizmann','ramalho','schanda','wintersteiger']
    printed=[r for r in tex_rows('12-floating-point.tex') if r[0].startswith('OptiMathSAT:') or r[0].startswith('Z3:')]
    assert len(printed)==3;export=[]
    for row,route in zip(printed,['fp','bvfp','bv']):
        calls=[r for r in fp if r['route']==route];assert len(calls)==1120
        for r in calls:
            record=raw[f'{int(r["index"]):02d}/{route}.final.json']
            assert r['adapter_status']==record['status']
            assert flag(r['paper_completed'])==(record['status']=='verified')
            if flag(r['paper_completed']):
                assert record['verification']['attainable']=='sat' and record['verification']['strictly_better']=='unsat'
        counts=[sum(flag(r['paper_completed']) for r in calls if r['group']==g) for g in groups]
        assert row[1:]==list(map(str,counts+[sum(counts)]))
        for g,n in zip(groups,counts):export.append(dict(route=route,group=g,instances=sum(r['group']==g for r in calls),verified=n))
    write_csv('paper/tables/12-floating-point.csv',export)
    reports['floating_point']=dict(calls=3360,verified={f:sum(flag(r['paper_completed']) for r in fp if r['route']==f) for f in ['fp','bvfp','bv']},passed=True)
    reports['primary_calls']=len(perf)+len(exact)+len(hilbert)+len(public)+len(disj)+len(irrational)+len(single)+len(maxsmt)+len(fp)
    assert reports['primary_calls']==10012
    return reports

def write_csv(path,rows):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def wide_table_exports():
    """CSV tables follow the printed row/column layout; call CSVs stay tidy."""
    def plain(s):
        s=s.replace(r'\varepsilon','epsilon').replace(r'\infty','infinity').replace(r'\,',' ')
        s=re.sub(r'\\sqrt\s*(\d+)',r'sqrt(\1)',s)
        s=re.sub(r'\\text\{([^{}]+)\}',r'\1',s)
        return s
    rows=[r for r in tex_rows('05-linear.tex') if re.match(r'(GAP|配置|背包|集合覆盖)\d+',r[0])]
    names=['instance','z3','optimathsat','cbc','highs','scip','gurobi','cplex','gecode','cpsat']
    write_csv('paper/tables/05-linear.csv',[dict(zip(names,map(plain,r))) for r in rows])
    rows=[r for r in tex_rows('06-jobshop.tex') if r[0] in ['7','8','9','10']]
    names=['jobs','z3','optimathsat','cbc-bigm','highs-bigm','scip-bigm','gurobi-bigm','gurobi-ind','cplex-bigm','cplex-ind','gecode','cpsat']
    write_csv('paper/tables/06-jobshop.csv',[dict(zip(names,map(plain,r))) for r in rows])
    rows=[r for r in tex_rows('07-large-coefficients.tex') if r[0] in ['OMT','CP','MILP']]
    names=['z3','optimathsat','cpsat','cbc','highs','scip','cplex','gurobi','scip-exact']
    write_csv('paper/tables/07-large-coefficients.csv',[dict(solver=n,total_per_exponent=10,**{f'correct_e{e}':int(v.split('/')[0]) for e,v in zip([40,54,60,200],r[2:])}) for n,r in zip(names,rows)])
    rows=[r for r in tex_rows('08-hilbert.tex') if r[0] in ['OMT','MILP']]
    names=['z3','optimathsat','cbc','highs','scip','gurobi','cplex']
    write_csv('paper/tables/08-hilbert.csv',[dict(solver=n,**{f'n{k}':v for k,v in zip([6,8,10,12,14,16],r[2:])}) for n,r in zip(names,rows)])
    rows=[r for r in tex_rows('09-nra-single.tex') if r[0].startswith(('\\max','\\min'))]
    cases=['A_sqrt2','A_sqrt5','B_5_9','B_9_25','C1_inf_unattained','C2_unbounded_below']
    names=['reference','z3','ocac','optimathsat','scipy','ipopt','gurobi','couenne']
    write_csv('paper/tables/09-nra-single.csv',[dict(case=c,**dict(zip(names,map(plain,r[1:])))) for c,r in zip(cases,rows)])
    rows=[r for r in tex_rows('10-nra-multi.tex') if len(r)==7 and re.match(r'\\mathrm\{[ABC]\}',r[0])]
    cases=['A_r5','A_r8','A_r13','B_a3_b3','B_a4_b6','B_a5_b8','C_r5_5','C_r29_5','C_r29_8']
    names=['reference','z3','ocac','optimathsat','gurobi','couenne']
    write_csv('paper/tables/10b-nra-irrational.csv',[dict(instance=c,**dict(zip(names,map(plain,r[1:])))) for c,r in zip(cases,rows)])
    rows=[r for r in tex_rows('11-maxsmt.tex') if len(r)==7 and r[0] in ['2','11','21']]
    names=['N','p','instances','z3-maxres','z3-wmax','oms-omt','oms-maxres']
    write_csv('paper/tables/11-maxsmt.csv',[dict(zip(names,map(plain,r))) for r in rows])
    rows=[r for r in tex_rows('12-floating-point.tex') if r[0].startswith(('OptiMathSAT:','Z3:'))]
    names=['route','griggio','heizmann','ramalho','schanda','wintersteiger','total']
    write_csv('paper/tables/12-floating-point.csv',[dict(zip(names,map(plain,r))) for r in rows])

def deep_checks():
    with tempfile.TemporaryDirectory(prefix='omt-current-audit-') as td:
        w=Path(td);materialize(w)
        with tarfile.open(ROOT/'benchmarks/floating-point/inputs.tar.gz') as t:
            for m in t:
                assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
                dest=w/'benchmarks/public_fp'/m.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(t.extractfile(m).read())
        # Cases are a derived join of final records, not another stored copy.
        selection=json.loads((w/'benchmarks/public_fp/selection-full.json').read_text())['selected']
        raw=load_json_members('results/floating-point/records.tar.gz')
        for i,s in enumerate(selection):
            case=dict(index=i,group=s['group'],upstream=s['upstream'],routes={form:raw[f'{i:02d}/{form}.final.json'] for form in ['fp','bvfp','bv']})
            p=w/'runs/public_fp_full_20261106_600s/cases'/f'{i:04d}.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(case))
        env=os.environ.copy();env.update(OMT_UNIFORM600_OUTPUT=str(w/BASE),OMT_NRA_TIMEOUT_S='600',OMT_NRA_WITNESS_TIMEOUT_S='600')
        for key,folder in [('PUBLIC','nra_public'),('DISJ','nra_disjunctive'),('IRR','nra_irrational'),('EXT','nra_extensions')]:env['OMT_NRA_'+key+'_OUTPUT']=str(w/BASE/folder)
        commands=[['audit_uniform600_20261106.py'],['audit_nra_public_20261102.py'],['audit_nra_disjunctive_20261102.py'],['audit_nra_irrational_20261102.py'],['audit_public_fp_20261106.py']]
        for args in commands:
            p=subprocess.run([sys.executable,str(w/'scripts'/args[0])]+args[1:],env=env,capture_output=True,text=True)
            assert p.returncode==0,(args,p.stdout[-1500:],p.stderr[-2500:])
            print('PASS original audit:',args[0],flush=True)
    return dict(passed=True,original_audits=5,optimizers_rerun=0)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--deep',action='store_true');args=p.parse_args()
    report=dict(preserved_bytes=byte_checks());print('PASS retained object hashes',flush=True)
    report['inputs']=input_checks();print('PASS complete input cohorts',flush=True)
    report['results']=table_checks();wide_table_exports();print('PASS all paper table/figure statistics',flush=True)
    if args.deep:report['deep']=deep_checks()
    report['passed']=True
    (ROOT/'paper/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
