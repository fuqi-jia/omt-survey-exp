#!/usr/bin/env python3
"""Known-answer semantic checks; these are not performance benchmark samples."""
import hashlib,json,tempfile
from pathlib import Path
import run_case as runner

CASES={
 'bv_unsigned':('bv','''(declare-fun x () (_ BitVec 8))
(assert (bvuge x #x80)) (maximize x) (check-sat)''',255),
 'maxsmt_weighted':('maxsmt','''(declare-fun x () Int)
(assert (and (<= 0 x) (<= x 1)))
(assert-soft (= x 0) :weight 1 :id weight.Auto)
(assert-soft (= x 1) :weight 3 :id weight.Auto)
(minimize weight.Auto) (check-sat)''',1),
 'fp_nan_zeros':('fp','''(declare-fun x () (_ FloatingPoint 3 4))
(assert (or (= x (_ -zero 3 4)) (= x (_ +zero 3 4)) (fp.isNaN x)))
(minimize x) (check-sat)''',None),
 'infeasible':('bv','''(declare-fun x () (_ BitVec 8))
(assert false) (maximize x) (check-sat)''',None),
}


def main():
 results=[]
 dest=runner.ROOT/'tools/full-campaign-deps';dest.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='qualification-',dir=dest) as directory:
  for name,(suite,text,expected) in CASES.items():
   out=Path(directory)/name;out.mkdir();source=out/'input.smt2';source.write_text(text)
   row=dict(suite=suite,path=source.relative_to(runner.ROOT).as_posix(),sha256=runner.sha(source))
   problem=runner.load_problem(row)
   variants={'bv':['oms_bv','z3_bv'],'fp':['oms_fp','z3_fpkey','z3_bv'],
             'maxsmt':['oms_maxres','oms_omt','z3_maxres','z3_wmax']}[suite]
   for variant in variants:
    result=runner.native_oms(problem,row,variant,out) if variant.startswith('oms') else runner.solve_z3(problem,row,variant)
    if name=='infeasible':
     assert result['status']=='infeasible',(name,variant,result)
    else:
     assert result['status']=='solver_claimed_optimal',(name,variant,result)
     checked=runner.verify(problem,row,variant,result)
     assert checked['status']=='verified_optimal',(name,variant,checked)
     if expected is not None:
      value=result['value'];actual=int(value['hex'],16) if value['kind']=='bv' else int(value['literal'])
      assert actual==expected,(name,variant,result)
     result['verification']=checked
    results.append(dict(case=name,variant=variant,result=result))
 path=runner.ROOT/'runs/full20261009/qualification.json'
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(dict(passed=True,checks=len(results),kind='known-answer interface and semantics checks',results=results),indent=2)+'\n')
 print('Passed',len(results),'known-answer semantic checks')

if __name__=='__main__':main()
