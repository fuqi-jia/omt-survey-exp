#!/usr/bin/env python3
"""Prepare inputs and original code in a separate workspace; run no solvers."""
from pathlib import Path
import argparse, json, shutil, tarfile

ROOT=Path(__file__).resolve().parents[1]

def unpack(source,destination):
    destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(ROOT/source) as t:
        for m in t:
            assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts,m.name
            p=destination/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',choices=['performance','numerical','nonlinear','maxsmt','floating-point'],required=True)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--tools',type=Path,help='Optional installed native solver directory; linked without modification')
    a=p.parse_args();w=a.workspace.resolve()
    assert w!=ROOT and ROOT not in w.parents or ROOT/'reproduced' in w.parents,'Use a separate workspace or reproduced/<name>'
    assert not w.exists(),'Choose a new workspace; existing results are never overwritten'
    w.mkdir(parents=True)
    with tarfile.open(ROOT/'reproduction/source.tar.gz') as t:
        for m in t:
            if not m.name.startswith(('scripts/','experiments/')):continue
            assert m.isfile() and '..' not in Path(m.name).parts
            dest=w/m.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(t.extractfile(m).read())
    if a.tools:
        (w/'tools').symlink_to(a.tools.resolve(),target_is_directory=True)
    commands=[]
    if a.study=='performance':
        out=w/'runs/paper_refresh_20261028'
        unpack('benchmarks/performance/inputs.tar.gz',out)
        shutil.copyfile(ROOT/'benchmarks/performance/manifest.json',out/'manifest.json')
        commands=[['python','scripts/paper_refresh_20261028.py','--workers','1'],
                  ['python','scripts/paper_refresh_20261028.py','--commercial','--workers','1']]
    elif a.study in ['numerical','nonlinear']:
        meta={}
        with tarfile.open(ROOT/'provenance/execution-records.tar.gz') as t:
            for m in t:
                if m.name.endswith('/model-definition-protocol.json'):meta[m.name.split('/')[-2]]=t.extractfile(m).read()
        for group,old in [('public','nra_public'),('disjunctive','nra_disjunctive'),('irrational','nra_irrational')]:
            legacy=w/'runs'/(old+'_20261102')
            unpack('benchmarks/nonlinear/'+group+'/models.tar.gz',legacy/'models')
            (legacy/'protocol.json').write_bytes(meta[old])
            if group!='public':unpack('benchmarks/nonlinear/'+group+'/models.tar.gz',w/'benchmarks'/('nra-'+group+'-20261102'))
        unpack('benchmarks/nonlinear/public/inputs.tar.gz',w/'benchmarks/minlplib-qcqp-20261102')
        commands=[['python','scripts/uniform600_20261106.py','prepare']]
        if a.study=='numerical':
            commands += [['python','scripts/uniform600_20261106.py','worker','--kind','numeric','--solver',solver,'--core','0'] for solver in ['z3','optimathsat','cpsat','cbc','highs','scip','scip-exact','gurobi','cplex']]
        else:
            commands += [['python','scripts/uniform600_20261106.py','batch','--workers','1','--exclude-gurobi']]
            commands += [['python','scripts/uniform600_20261106.py','worker','--kind',kind,'--solver','gurobi','--core','0'] for kind in ['base','public','disjunctive','irrational']]
    elif a.study=='maxsmt':
        out=w/'runs/maxsmt_cgm_server_20261103';out.mkdir(parents=True)
        unpack('benchmarks/maxsmt/inputs.tar.gz',out/'inputs')
        shutil.copyfile(ROOT/'benchmarks/maxsmt/manifest.json',out/'manifest.json')
        # A small launcher only relocates the original engine; target construction,
        # parsing, witness checking and solver parameters remain in its source.
        (w/'run-maxsmt.py').write_text('''from pathlib import Path
import argparse, hashlib, json, os, shutil, sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'scripts'))
import maxsmt_public_20261103 as exp
p=argparse.ArgumentParser();p.add_argument('action',choices=['run','summarize','table']);p.add_argument('--cores',default='0');a=p.parse_args()
exp.RUN=root/'runs/maxsmt_cgm_server_20261103'
binary=shutil.which('z3');assert binary,'Put Z3 5.3.3 on PATH'
exp.Z3=Path(binary);exp.CORES=tuple(map(int,a.cores.split(',')))
manifest=json.loads((exp.RUN/'manifest.json').read_text())
manifest['execution_environment']={'reproduction':True,'hostname':__import__('platform').node()}
manifest['cores']=exp.CORES
manifest['binaries']={str(b):hashlib.sha256(b.read_bytes()).hexdigest() for b in [exp.Z3,exp.OMS]}
exp.save(exp.RUN/'manifest.json',manifest)
{'run':exp.run,'summarize':exp.summarize,'table':exp.table}[a.action]()
''')
        commands=[['python','run-maxsmt.py','run','--cores','0'],['python','run-maxsmt.py','summarize'],['python','run-maxsmt.py','table']]
    else:
        destination=w/'benchmarks/public_fp'
        unpack('benchmarks/floating-point/inputs.tar.gz',destination)
        shutil.copyfile(ROOT/'benchmarks/floating-point/selection.json',destination/'selection-full.json')
        commands=[['python','scripts/public_fp_full_20261106.py','--workers','1']]
    (w/'commands.json').write_text(json.dumps(dict(study=a.study,working_directory=str(w),commands=commands),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(prepared=str(w),solver_calls_started=0,commands=commands),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
