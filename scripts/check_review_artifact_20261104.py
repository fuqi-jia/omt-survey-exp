#!/usr/bin/env python3
"""Check archived evidence without a solver or scientific Python packages."""
from collections import Counter,defaultdict
import csv
from decimal import Decimal,localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'artifacts/review-20261104'
D=ROOT/'runs/review_diagnostics_20261104'
def read(path):return json.loads((ROOT/path).read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(path):return list(csv.DictReader((ROOT/path).open()))

def main():
    cases=read('artifacts/review-20261104/case-index.json')
    for case in cases:
        for field in ['input','driver','raw','diagnostic']:
            p=ROOT/case[field];assert p.is_file(),p
            assert digest(p)==case[field+'_sha256'],p
    strict=read('runs/review_diagnostics_20261104/optimathsat/C1_inf_unattained.json')
    assert strict['objective_status_code']==3 and strict['values']['optimum']['epsilon']==1
    assert strict['model']=={'x':'2'}
    assert strict['original_cli_sha256']==digest(ROOT/strict['original_cli_input'])
    assert '(> (* x x) 2)' in (ROOT/strict['original_cli_input']).read_text()
    assert any('not' in f and '<=' in f and '*_rat' in f for f in strict['asserted_formulas'])
    assert Fraction(strict['model']['x'])**2>2
    a5=read('runs/review_diagnostics_20261104/optimathsat/A_r5.json')
    assert a5['objective_status_code']==3
    with localcontext() as context:
        context.prec=50
        assert Decimal(1)<Decimal(2).sqrt()
        assert Decimal(3)<(3*Decimal(7).sqrt()-Decimal(3).sqrt())/2
    h=read('runs/review_diagnostics_20261103/hilbert/result.json')
    x=h['rounded_vector'];n=h['n']
    residual=max(abs(sum(Fraction(x[j]-1,i+j+1) for j in range(n))) for i in range(n))
    assert residual==Fraction(1,10)==Fraction(h['exact_residual_at_rounded_vector'])
    assert h['status_code']==2
    for solver in ['scip','highs']:
        for encoding in ['original','small']:
            r=read(f'runs/review_diagnostics_20261104/bigcoeff/{solver}/{encoding}/result.json')
            inst=r['input_instance'];selected=r['exact_validation']['selected'];n=inst['n']
            objective=sum(inst['val'][i] for i in selected)
            truth=max(sum(inst['val'][i] for i in range(n) if mask>>i&1) for mask in range(2**n) if sum(inst['w'][i] for i in range(n) if mask>>i&1)<=inst['C'])
            assert truth==inst['opt'] and objective==r['exact_validation']['value']
            assert truth-objective==(0 if encoding=='small' else 6 if solver=='scip' else 1)
            assert r['cpu_affinity']==[0] and r['memory_limit_bytes']==4*1024**3
    cgm=rows('runs/review_diagnostics_20261104/cgm/results.csv')
    assert len(cgm)==4796
    completed=Counter(r['config'] for r in cgm if r['paper_classification']=='completed')
    assert dict(completed)=={'z3-maxres':1199,'z3-wmax':957,'oms-omt':1037,'oms-maxres':1130}
    assert Counter(r['config'] for r in cgm if r['adapter_status']=='unsat')==Counter({c:41 for c in completed})
    fp=rows('runs/review_diagnostics_20261104/fp/results.csv');assert len(fp)==3360
    assert Counter(r['route'] for r in fp if r['paper_completed']=='True')==Counter(fp=568,bvfp=622,bv=288)
    assert all(float(r['solve_s'])<=30 and r['attainable']=='sat' and r['strictly_better']=='unsat' for r in fp if r['paper_completed']=='True')
    for path in {r['record'] for r in fp if r['paper_completed']=='True'}:
        for result in read(path)['routes'].values():
            if result['status']=='verified':
                v=result['verification'];assert max(v['attainable_s'],v['strictly_better_s'])<=30
    for meta in [A/'fp-input-archive.json',D/'cgm/input-archive.json',D/'performance/input-archive.json']:
        r=json.loads(meta.read_text());p=ROOT/r['path'];assert p.stat().st_size==r['bytes'] and digest(p)==r['sha256']
    checked=0
    manifest=A/'SHA256SUMS'
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            expected,path=line.split('  ',1);assert digest(ROOT/path)==expected,path;checked+=1
    report=dict(passed=True,diagnostic_chains=len(cases),cgm_calls=4796,fp_cases=1120,checked_snapshot_files=checked)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
