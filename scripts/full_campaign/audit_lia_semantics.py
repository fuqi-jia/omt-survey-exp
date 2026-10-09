#!/usr/bin/env python3
"""Recheck a concrete source-level counterexample to BV/LIA equivalence.

This certificate is a semantic example, not a selected performance experiment;
the complete manifests still govern the two full runs.
"""
import json
from pathlib import Path
import run_case as common
import run_lia_diagnostic as diagnostic
import z3

root = common.ROOT
rows = [json.loads(s) for s in (common.DATA/'manifests/bv_lia.jsonl').read_text().splitlines()]
row = next(r for r in rows if r['id'] == 'e44850302daf521e186a')
path = root/row['path']
assert common.sha(path) == row['sha256']
opt, targets = diagnostic.parse_input(path)
parameter = z3.Int('__jos_unbounded_parameter')
fixed = {'x0_0':0, 'y0_0':1, 'x1_0':3, 'y1_0':2, 'even0':1, 'even1':1}
substitution = [(z3.Int(k), z3.IntVal(v)) for k,v in fixed.items()]
substitution += [(z3.Int(name), parameter) for sense,name in targets]
assert all(sense == 'maximize' for sense,name in targets)
substituted = z3.substitute(z3.And(*opt.assertions()), *substitution)
body = z3.simplify(substituted)
assert z3.is_true(body)
first = z3.simplify(z3.substitute(-opt.objectives()[0], *substitution))
assert z3.eq(first, parameter)
check = z3.Solver()
check.add(z3.Not(substituted))
assert check.check() == z3.unsat
bv_rows = [json.loads(s) for s in (common.DATA/'manifests/bv.jsonl').read_text().splitlines()]
bv_row = next(r for r in bv_rows if r['id'] == '7fa59c1e572b0cf322ce')
bv = common.load_problem(bv_row)
assert bv['target'].size() == 6 and bv['sense'] == 'maximize'
proof = dict(input=row, bv_input=bv_row, objective_count=len(targets), fixed_assignment=fixed,
    all_objectives='arbitrary integer parameter t', substituted_hard_constraints=body.sexpr(),
    first_maximized_objective=first.sexpr(), bv_unsigned_domain=[0,63],
    verification='Negation of substituted hard constraints is UNSAT; the first integer objective equals arbitrary t',
    conclusion='This distributed LIA companion is unbounded above, whereas the original BV target has a finite domain',
    z3=z3.get_version_string(), certificate_script_sha256=common.sha(Path(__file__)))
out = root/'runs/full20261009/lia-source-diagnostic'
out.mkdir(parents=True, exist_ok=True)
(out/'parametric-unbounded-proof.json').write_text(json.dumps(proof, indent=2)+'\n')
(out/'parametric-unbounded-proof.smt2').write_text(check.to_smt2())
print('Unbounded original LIA certified; original BV has a six-bit unsigned target')
