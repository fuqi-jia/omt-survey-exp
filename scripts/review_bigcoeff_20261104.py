#!/usr/bin/env python3
"""Retain native statuses and exact objective checks for representative 2**40 cases."""
import argparse
import contextlib
import json
import os
import resource
from pathlib import Path
import sys
import pulp
import exact_experiment as exact

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/review_diagnostics_20261104/bigcoeff'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('solver',choices=['scip','highs'])
    args=parser.parse_args()
    os.sched_setaffinity(0,{0})
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    n,seed=(8,0) if args.solver=='scip' else (12,4)
    inst=exact.gen(n,seed,2**40)
    for encoding in ['original','small']:
        folder=OUT/args.solver/encoding
        folder.mkdir(parents=True,exist_ok=True)
        coefficients=inst['val'] if encoding=='original' else [85+v-2**40 for v in inst['val']]
        model=pulp.LpProblem('bigcoeff',pulp.LpMaximize)
        x=[pulp.LpVariable(f'x{i}',cat='Binary') for i in range(n)]
        model+=pulp.lpSum(coefficients[i]*x[i] for i in range(n))
        model+=pulp.lpSum(inst['w'][i]*x[i] for i in range(n))<=inst['C']
        model.writeLP(str(folder/'input.lp'))
        solver=(pulp.SCIP_PY(msg=True,timeLimit=120,gapRel=0,gapAbs=0,logPath=str(folder/'native.log'))
                if args.solver=='scip' else pulp.HiGHS(msg=True,timeLimit=120,gapRel=0,gapAbs=0,log_file=str(folder/'native.log')))
        model.solve(solver)
        native=model.solverModel
        if args.solver=='scip':
            status=str(native.getStatus()); obj=native.getObjVal(); bound=native.getDualbound();gap=native.getGap()
            native.writeParams(str(folder/'settings.set'))
            version='.'.join(str(v) for v in [native.getMajorVersion(),native.getMinorVersion(),native.getTechVersion()])
        else:
            status=str(native.getModelStatus()); info=native.getInfo();obj=native.getObjectiveValue();bound=info.mip_dual_bound;gap=info.mip_gap;version=native.version()
            native.writeOptions(str(folder/'settings.set'))
        selected=[i for i in range(n) if (x[i].value() or 0)>0.5]
        checked=exact._classify(selected,inst)
        result=dict(solver=args.solver,version=version,encoding=encoding,input_instance=inst,
                    cpu_affinity=sorted(os.sched_getaffinity(0)),memory_limit_bytes=4*1024**3,time_limit_s=120,
                    native_status=status,native_objective=obj,native_bound=bound,native_mip_gap=gap,
                    adapter_status=pulp.LpStatus[model.status],adapter_solution_status=model.sol_status,
                    paper_classification=checked['status'],exact_validation=checked,
                    scope='Targeted diagnostic; original paper cohort is preserved.')
        (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(args.solver,encoding,status,checked,flush=True)

if __name__=='__main__': main()
