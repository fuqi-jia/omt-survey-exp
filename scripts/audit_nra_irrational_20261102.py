#!/usr/bin/env python3
"""Audit all predeclared calls, analytic references and native exact values."""

from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import tempfile

import nra_irrational_20261102 as spec
import nra_public_20261102 as common


def decimal_reference(model):
    with localcontext() as ctx:
        ctx.prec=80;p=model['parameters']
        def branch(r,positive=False):
            return (3*Decimal(r+2).sqrt()+(1 if positive else -1)*Decimal(r-2).sqrt())/2
        if model['family']=='A':value=branch(p['r'])
        elif model['family']=='B':value=-(Decimal(p['a'])+Decimal(p['b']-1).sqrt()).sqrt()+Decimal('0.1')
        else:value=min(branch(p['r0']),branch(p['r1'],True))
        return str(value)


def recover_couenne(model,folder,result):
    solutions=list(folder.glob('*.sol'));inputs=list(folder.glob('*.nl'))
    if result['status']!='ERROR' or len(solutions)!=1 or len(inputs)!=1:return result
    import pyomo.environ as p
    from pyomo.opt import ReaderFactory
    m=spec.pyomo_model(model)
    with tempfile.TemporaryDirectory(prefix='gomt-irrational-nl-check-') as td:
        filename,smap=m.write(str(Path(td)/'input.nl'))
        assert Path(filename).read_bytes()==inputs[0].read_bytes()
        with ReaderFactory('sol') as reader:solution=reader(str(solutions[0]))
        solution._smap_id=smap;m.solutions.load_from(solution)
        x=[p.value(m.x[i]) for i in range(len(model['variables']))]
    common.save(folder/'solver-run.json',result)
    result.update(native_status=result['status'],status='NATIVE_ERROR_WITH_SOLUTION',x=x,
                  candidate_source=solutions[0].name,nl_column_mapping_verified=True,
                  candidate_sha256=hashlib.sha256(solutions[0].read_bytes()).hexdigest(),
                  **spec.assess(model,x,model['reference']))
    result['optimization_hit']=result['reference_hit']
    return result


def main():
    rows=[];models={};proofs=[];z3=common.load_z3()
    for path in sorted((spec.OUT/'models').glob('*.json')):
        model=json.loads(path.read_text());name=model['name'];models[name]=model
        assert path.read_bytes()==(spec.BENCH/path.name).read_bytes()
        independently=decimal_reference(model)
        assert abs(float(independently)-model['reference'])<1e-14
        exact,vector=spec.exact_formula(model)
        assert z3.is_algebraic_value(exact)
        assert spec.assess(model,model['reference_vector'],model['reference'])['reference_hit']
        cert=model['nonconvexity_certificate']
        assert all(spec.assess(model,v,model['reference'])['feasible'] for v in cert['endpoints'])
        assert not spec.assess(model,cert['midpoint'],model['reference'])['feasible']
        labels=['z3','ocac','optimathsat','gurobi','couenne']
        if model['family']!='C':labels+=['ipopt_I','ipopt_II','scipy_I','scipy_II']
        for label in labels:
            folder=spec.OUT/label/name;result=json.loads((folder/'result.json').read_text())
            assert result['status']!='WORKER_ERROR',(label,name)
            if result.get('model_sha256'):
                assert result['model_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            if label=='couenne':result=recover_couenne(model,folder,result)
            if label in ('z3','ocac','optimathsat'):
                try:
                    value,raw=spec.parse_exact_objective((folder/'stdout.txt').read_text())
                    result['reported_exact_expression']=raw
                    result['reported_value']=common.z3_float(value) if value is not None else None
                    result['exact_expression_matches_reference']=value is not None and z3.is_true(z3.simplify(value==exact))
                    result.pop('exact_parse_error',None)
                    result['optimization_hit']=result['reference_hit'] and value is not None and abs(common.z3_float(value)-model['reference'])/max(1,abs(model['reference']))<=1e-6
                except Exception as exc:
                    raise AssertionError((label,name,'unreadable native objective',repr(exc))) from exc
            checked=spec.assess(model,result.get('x'),model['reference'])
            assert checked['reference_hit']==result['reference_hit']
            assert checked['feasible']==result['feasible']
            assert result['elapsed_s']<=201
            native_ok=(result['status'] in ('RETURNED','optimal','SUCCESS','2'))
            if label in ('z3','ocac','optimathsat'):
                native_ok=native_ok and (folder/'stdout.txt').read_text().strip().splitlines()[:1]==['sat']
            result['correct_optimal_return']=bool(result['optimization_hit'] and native_ok)
            common.save(folder/'result.json',result);rows.append(dict(result,label=label,family=model['family']))
        proofs.append(dict(instance=name,decimal_reference=independently,irrational=True,nonconvex=True))
    assert len(models)==9 and len(rows)==69
    summary={}
    for label in ['z3','ocac','optimathsat','gurobi','couenne','ipopt_I','ipopt_II','scipy_I','scipy_II']:
        selected=[r for r in rows if r['label']==label]
        summary[label]=dict(total=len(selected),hits=sum(r['optimization_hit'] for r in selected),
            correct_optimal_returns=sum(r['correct_optimal_return'] for r in selected),
            exact_values=sum(r.get('exact_expression_matches_reference',False) for r in selected),
            by_family={f:sum(r['optimization_hit'] for r in selected if r['family']==f) for f in 'ABC'},
            statuses=dict(Counter(r['status'] for r in selected)))
    common.save(spec.OUT/'results.json',rows)
    common.save(spec.OUT/'summary.json',summary)
    common.save(spec.OUT/'reference-audit.json',proofs)
    common.save(spec.OUT/'delivery-audit.json',dict(passed=True,total_calls=69,instances=9,
        all_irrational=True,all_nonconvex=True,all_results_checked=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(summary,indent=2));print('PASS: 69 calls, nine irrational optima, nine nonconvexity certificates')


if __name__=='__main__':main()
