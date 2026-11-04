#!/usr/bin/env python3
"""Actual returned values/statuses for all nine nonconvex irrational cases."""

import json

import nra_irrational_20261102 as spec


def main():
    assert json.loads((spec.OUT/'delivery-audit.json').read_text())['passed']
    names=['A_r5','A_r8','A_r13','B_a3_b3','B_a4_b6','B_a5_b8','C_r5_5','C_r29_5','C_r29_8']
    labels=[r'$\mathrm{A}_{5}$',r'$\mathrm{A}_{8}$',r'$\mathrm{A}_{13}$',
            r'$\mathrm{B}_{3,3}$',r'$\mathrm{B}_{4,6}$',r'$\mathrm{B}_{5,8}$',
            r'$\mathrm{C}_{5,5}$',r'$\mathrm{C}_{29,5}$',r'$\mathrm{C}_{29,8}$']
    lines=[r'\begin{table}[H]',r'\centering',r'\caption{无理最优值非凸算例的返回结果 (数值保留八位小数)}',
           r'\label{tab:exp-nra-irrational}',r'\footnotesize',r'\setlength{\tabcolsep}{4pt}',
           r'\begin{tabular}{@{}lrrrrrr@{}}',r'\toprule',
           r'实例 & 参考最优值 & Z3 & OCAC & OptiM. & Gurobi & Couenne \\',r'\midrule']
    for index,(name,label) in enumerate(zip(names,labels)):
        if index in (3,6):lines.append(r'\midrule')
        model=json.loads((spec.OUT/'models'/(name+'.json')).read_text());values=[]
        for solver in ('z3','ocac','optimathsat','gurobi','couenne'):
            r=json.loads((spec.OUT/solver/name/'result.json').read_text())
            if r['status']=='TIMEOUT':value='超时'
            elif r['status']=='infeasible':value='判不可行'
            elif solver in ('z3','ocac','optimathsat'):
                if r.get('reported_value') is not None:value='$'+f"{r['reported_value']:.8f}"+'$'
                elif r.get('reported_exact_expression')=='(+ 3 epsilon)':value=r'$3+\varepsilon$'
                else:raise ValueError((solver,name,r))
            elif r.get('objective') is not None:value='$'+f"{r['objective']:.8f}"+'$'
            else:value='失败'
            values.append(value)
        lines.append(label+' & $'+f"{model['reference']:.8f}"+'$ & '+' & '.join(values)+r' \\')
    lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (spec.OUT/'table.tex').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
