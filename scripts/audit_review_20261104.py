#!/usr/bin/env python3
"""Audit published cohorts, preserve denominators, and expose per-result provenance."""
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile
import maxsmt_public_20261103 as cgm

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/review_diagnostics_20261104'

def save(name,data):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def write_csv(name,rows):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def rel(p):return p.relative_to(ROOT).as_posix()
def sha(data):return hashlib.sha256(data).hexdigest()

def audit_cgm():
    run=ROOT/'runs/maxsmt_cgm_server_20261103'
    manifest=json.loads((run/'manifest.json').read_text())
    rows=[]; grouped=defaultdict(Counter); byconfig=defaultdict(Counter)
    for cell in manifest['instances']:
        for config in manifest['configs']:
            folder=run/'results'/cell['id']/config;r=json.loads((folder/'result.json').read_text())
            raw=(folder/'stdout.txt').read_text()
            native=next((l.strip() for l in raw.splitlines() if l.strip() in ['sat','unsat','unknown']),'no status token')
            status=r['status'];grouped[(cell['replicas'],cell['preferences_per_replica'],config)][status]+=1;byconfig[config][status]+=1
            if status=='optimal': assert r['validation']['feasible'] and r['validation']['recomputed_costs']==r['objective']
            rows.append(dict(instance=cell['id'],N=cell['replicas'],p=cell['preferences_per_replica'],config=config,archive_member=cell['archive_member'],source_sha256=cell['source_sha256'],input_sha256=r['input_sha256'],native_status_token=native,returncode=r['returncode'],adapter_status=status,paper_classification='completed' if status in ['optimal','unsat'] else 'unfinished',elapsed_s=r['elapsed_s'],objective=json.dumps(r.get('objective')),result=rel(folder/'result.json'),stdout=rel(folder/'stdout.txt'),stderr=rel(folder/'stderr.txt')))
    assert len(rows)==4796
    assert {k:v['optimal']+v['unsat'] for k,v in byconfig.items()}=={'z3-maxres':1199,'z3-wmax':957,'oms-omt':1037,'oms-maxres':1130}
    assert all(v['unsat']==41 for v in byconfig.values())
    write_csv('cgm/results.csv',rows)
    breakdown=[dict(N=n,p=p,config=c,optimal=v['optimal'],hard_unsat=v['unsat'],unfinished=sum(v.values())-v['optimal']-v['unsat']) for (n,p,c),v in sorted(grouped.items())]
    write_csv('cgm/breakdown.csv',breakdown)
    save('cgm/audit.json',dict(passed=True,instances=1199,calls=4796,excluded=manifest['excluded'],by_config={k:dict(v) for k,v in byconfig.items()}))
    print('PASS CGM 4796 statuses; hard UNSAT=41 per configuration',flush=True)

def audit_fp():
    run=ROOT/'runs/public_fp_full_20261030';rows=[];counts=defaultdict(Counter);over=[];verification_over=[]
    for p in sorted((run/'cases').glob('*.json')):
        case=json.loads(p.read_text())
        for route,r in case['routes'].items():
            v=r.get('verification',{});counts[route][r['status']]+=1
            if r['status']=='verified':
                assert v['attainable']=='sat' and v['strictly_better']=='unsat'
                if r['solve_s']>30:over.append([case['index'],route,r['solve_s']])
                if max(v.get('attainable_s',0),v.get('strictly_better_s',0))>30:verification_over.append([case['index'],route])
            rows.append(dict(index=case['index'],group=case['group'],source=case['upstream'],route=route,adapter_status=r['status'],paper_completed=r['status']=='verified',solve_s=r.get('solve_s'),attainable=v.get('attainable'),strictly_better=v.get('strictly_better'),verification_value=v.get('value'),record=rel(p),raw_archive=rel(run/'raw-logs.tar.gz'),raw_member_prefix=f'{case["index"]:02d}/'))
    assert len(rows)==3360
    assert {k:v['verified'] for k,v in counts.items()}=={'fp':568,'bvfp':622,'bv':288}
    assert not over and not verification_over
    write_csv('fp/results.csv',rows)
    save('fp/budget-audit.json',dict(passed=True,cases=1120,routes=3,status_counts={k:dict(v) for k,v in counts.items()},completed_query_over_30_s=over,completed_verification_query_over_30_s=verification_over,timing=dict(native_oms_process_s=30,z3_prepare_process_s=35,z3_optimize_query_s=30,z3_solve_process_s=35,verification_each_query_s=30,verification_process_s=65),verified_definition='attainable SAT and strictly-better UNSAT under original FP constraints; native fp order or declared non-NaN BV key order'))
    print('PASS FP counts 568/622/288; no counted solve over 30 seconds',flush=True)

def audit_nra():
    import nra_public_20261102 as nra
    import nra_disjunctive_20261102 as disj
    rows=[];counts=defaultdict(Counter)
    for module in [nra,disj]:
        for modelpath in sorted((module.OUT/'models').glob('*.json')):
            model=json.loads(modelpath.read_text());name=modelpath.stem
            for solver in ['z3','ocac','optimathsat','scipy','ipopt','gurobi','couenne']:
                folder=module.OUT/solver/name;p=folder/'result.json'
                if not p.exists():continue
                r=json.loads(p.read_text());checked=module.assess(model,r.get('x'),model['reference'])
                assert checked['feasible']==r['feasible'] and checked['reference_hit']==r['reference_hit'],(name,solver)
                category=('reference_hit' if checked['reference_hit'] else 'feasible_below_quality_threshold' if checked['feasible'] else 'no_candidate' if r.get('x') is None else 'infeasible_candidate')
                counts[(module.OUT.name,solver)][category]+=1
                rows.append(dict(cohort=module.OUT.name,instance=name,solver=solver,adapter_status=r['status'],recorded_native_status=r.get('native_status'),candidate_present=r.get('x') is not None,candidate_source=r.get('candidate_source','interface model / returned vector or witness reconstruction' if r.get('x') is not None else ''),category=category,feasible=r['feasible'],reference_hit=r['reference_hit'],objective=r.get('objective'),reference=model['reference'],result=rel(p),model=rel(modelpath)))
    assert len([r for r in rows if r['cohort']==nra.OUT.name])==301
    expected={'z3':35,'ocac':22,'optimathsat':28,'scipy':22,'ipopt':28,'gurobi':43,'couenne':42}
    assert {s:counts[(nra.OUT.name,s)]['reference_hit'] for s in expected}==expected
    write_csv('nra/candidates.csv',rows)
    breakdown=[dict(cohort=c,solver=s,**{k:v[k] for k in ['reference_hit','feasible_below_quality_threshold','infeasible_candidate','no_candidate']}) for (c,s),v in sorted(counts.items())]
    write_csv('nra/breakdown.csv',breakdown)
    save('nra/audit.json',dict(passed=True,records=len(rows),public_reference_hits=expected))
    print('PASS NRA candidate classifications',flush=True)

def archive_cgm_inputs():
    run=ROOT/'runs/maxsmt_cgm_server_20261103';m=json.loads((run/'manifest.json').read_text())
    dest=ROOT/'benchmarks/maxsmt-cgm-20261103';dest.mkdir(parents=True,exist_ok=True)
    archive=dest/'inputs.tar.gz'
    with zipfile.ZipFile(cgm.ARCHIVE) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read('exp2.zip'))) as inner:
            with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
                for k,cell in enumerate(m['instances']):
                    data=inner.read(cell['archive_member']);assert sha(data)==cell['source_sha256']
                    parsed=cgm.parse(data.decode())
                    inputs={'original.smt2':data}
                    for config in m['configs']:
                        encoded,hard,_,_=cgm.encode(data.decode(),config,parsed)
                        r=json.loads((run/'results'/cell['id']/config/'result.json').read_text())
                        encoded=encoded.encode();assert sha(encoded)==r['input_sha256'],(cell['id'],config)
                        inputs[config+'.smt2']=encoded;inputs['hard.smt2']=hard.encode()
                    for name,data in inputs.items():
                        info=tarfile.TarInfo(cell['id']+'/'+name);info.size=len(data);info.mtime=0;info.mode=0o644
                        tar.addfile(info,io.BytesIO(data))
                    if k%200==0:print('CGM encoded input hashes verified',k+1,flush=True)
    save('cgm/input-archive.json',dict(path=rel(archive),sha256=sha(archive.read_bytes()),bytes=archive.stat().st_size,original_instances=1199,encoded_inputs=4796,all_input_hashes_match_server_runs=True,source_archive_url=m['source_url'],source_archive_sha256=m['archive_sha256']))
    print('PASS CGM complete inputs archive',archive.stat().st_size,flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--archive-inputs',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    audit_cgm();audit_fp();audit_nra()
    if args.archive_inputs:archive_cgm_inputs()
