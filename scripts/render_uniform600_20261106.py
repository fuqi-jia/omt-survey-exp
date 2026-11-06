#!/usr/bin/env python3
"""Export audited cells for the manuscript's numerical/NRA result tables."""
import json
from pathlib import Path
from uniform600_20261106 import OUT, save


def read(path):
    return json.loads(path.read_text())


def main():
    assert read(OUT / 'delivery-audit.json')['passed']
    public = read(OUT / 'nra_public/table.json')
    disj = read(OUT / 'nra_disjunctive/summary.json')
    labels = [('z3', 'Z3'), ('ocac', 'OCAC'), ('optimathsat', 'OptiMathSAT'),
              ('scipy', 'SLSQP'), ('ipopt', 'IPOPT'), ('gurobi', 'Gurobi'), ('couenne', 'Couenne')]
    rows, values = [], {}
    for solver, label in labels:
        p = [public[solver][str(n)] for n in [2, 3, 4, 5]]
        d = [disj[solver][str(n)]['hits'] for n in [4, 8, 12]] if solver in disj else None
        cells = p + [sum(p)] + (d + [sum(d)] if d else ['--'] * 4)
        rows.append(label + ' & ' + ' & '.join(map(str, cells)) + r' \\')
        values[solver] = dict(public=p + [sum(p)], disjunctive=d + [sum(d)] if d else None)
    (OUT / 'nra-multi-a-rows.tex').write_text('\n'.join(rows) + '\n')
    irrational = {}
    names = ['A_r5', 'A_r8', 'A_r13', 'B_a3_b3', 'B_a4_b6', 'B_a5_b8', 'C_r5_5', 'C_r29_5', 'C_r29_8']
    for name in names:
        irrational[name] = {}
        for solver in ['z3', 'ocac', 'optimathsat', 'gurobi', 'couenne']:
            result = read(OUT / 'nra_irrational' / solver / name / 'result.json')
            if result['status'] == 'TIMEOUT':
                displayed = '超时'
            elif solver == 'couenne' and result['status'] == 'infeasible':
                displayed = '报不可行'
            elif solver == 'optimathsat' and name == 'A_r5' and result.get('reported_exact_expression') == '(+ 3 epsilon)':
                assert read(OUT / 'diagnostics/optimathsat/A_r5.json')['objective_status'] == 'SAT_OPTIMAL'
                displayed = r'$3+\varepsilon$ (OPT)'
            else:
                value = result.get('reported_value') if solver in ['z3', 'ocac', 'optimathsat'] else result.get('objective')
                if value is None:
                    raise ValueError((solver, name, result['status'], result.get('reported_exact_expression')))
                displayed = f'${value:.8f}$'
            irrational[name][solver] = dict(display=displayed, status=result['status'],
                record=str((OUT / 'nra_irrational' / solver / name / 'result.json').relative_to(OUT)))
    save(OUT / 'paper-cells.json', dict(multivariable=values, irrational=irrational,
         numerical=read(OUT / 'numerical-audit.json'), primary_calls=863, auxiliary_api_calls=2))
    index = {
        'tab:exp-exact': dict(data='exact/*/results-*.json', instances='instances/knapsack_*.json', calls=360),
        'tab:exp-illcond': dict(data='illcond/*/results-*.json', instances='instances/hilbert_*.json',
                              matrix_characteristics='hilbert_condition_numbers.json', calls=42),
        'tab:exp-nra': dict(data=['nra_base/', 'nra_extensions/'], api_states='diagnostics/optimathsat/', calls=46),
        'tab:exp-nra-multi(a)': dict(data=['nra_public/*/*/result.json', 'nra_disjunctive/*/*/result.json'], calls=346),
        'tab:exp-nra-multi(b)': dict(data='nra_irrational/*/*/result.json', calls=69),
    }
    save(OUT / 'paper-result-index.json', index)
    print(json.dumps(values, indent=2))


if __name__ == '__main__':
    main()
