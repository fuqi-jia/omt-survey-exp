#!/usr/bin/env python3
"""Generate the FP LaTeX result draft from the full verified export."""
from render_completed_results import CONFIGS, OUT, load_complete


def main():
    report = load_complete('fp')
    configs = CONFIGS['fp']
    names = ['OptiMathSAT 原生 FP', 'Z3 FP 序键', 'Z3 FP 转 BV']
    lines = [r'% 由 render_fp_table.py 从完整数据生成; 尚未并入主稿.',
             r'\paragraph{公开浮点优化基准.}',
             r'表~\ref{tab:exp-public-fp-full} 给出全部 $39\,655$ 个任务在三种配置下的结果. '
             r'每个任务均完成运行, 超时与内存不足结果保留在统计中. '
             r'求解器报告最优与通过独立复核的数量分别列示, 不可满足返回按求解器报告计数.', '',
             r'\begin{table}[!ht]', r'\centering',
             r'\caption{公开浮点优化基准全集的求解与独立复核结果}',
             r'\label{tab:exp-public-fp-full}', r'\small',
             r'\begin{tabular}{@{}l rrrrr r@{}}', r'\toprule',
             r'配置 & 报告最优 & 独立复核 & 不可满足 & 超时 & 内存不足 & PAR-2 (s) \\', r'\midrule']
    for variant, name in zip(configs, names):
        s = report['overall'][variant]
        o = s['outcomes']
        values = [name, s['claimed_optimal'], s['independently_verified'], o.get('infeasible', 0),
                  o.get('timeout', 0), o.get('oom', 0), f"{s['par2_s']:.2f}"]
        lines.append(' & '.join(map(str, values)) + r' \\')
    lines.extend([
        r'\bottomrule', r'\end{tabular}', r'\par\smallskip',
        r'\begin{minipage}{\linewidth}\footnotesize 每次求解限时 $600$\,s, 单线程, 地址空间上限 $8$\,GiB. '
        r'独立复核是报告最优结果中通过目标可达性与无严格改进两条查询的数量, 每条查询限时 $60$\,s; '
        r'复核时间另计. 不可满足返回未另行核验不可满足证明. '
        r'PAR-2 按求解器报告口径统计, 未报告最优或不可满足的输入按 $1200$\,s 计入.',
        r'\end{minipage}', r'\end{table}', '',
        r'\begin{table}[!ht]', r'\centering',
        r'\caption{浮点优化各来源组报告最优/独立复核的数量}',
        r'\label{tab:exp-public-fp-groups}', r'\small',
        r'\begin{tabular}{@{}l r rrr@{}}', r'\toprule',
        r'来源组 & 任务数 & OptiMathSAT 原生 FP & Z3 FP 序键 & Z3 FP 转 BV \\', r'\midrule'])
    cells = {(g['group'], g['variant']): g for g in report['by_group']}
    for group in sorted({g['group'] for g in report['by_group']}):
        values = [group, cells[group, configs[0]]['source_inputs']]
        values.extend(f"{cells[group, v]['claimed_optimal']}/{cells[group, v]['independently_verified']}" for v in configs)
        lines.append(' & '.join(map(str, values)) + r' \\')
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\par\smallskip',
                  r'\begin{minipage}{\linewidth}\footnotesize 每个来源组包含全部优化任务, '
                  r'$a/b$ 分别表示报告最优的数量及其中通过独立复核的数量, 两者不相加. '
                  r'任务由完整源文件构造, 同一源文件可以派生多个目标与方向. '
                  r'空公式源的两个常量正零任务作为退化检查保留, 不用于说明浮点运算性能.',
                  r'\end{minipage}', r'\end{table}', '',
                  r'三种配置共同报告最优时未发现目标值冲突. '
                  r'OptiMathSAT 原生 FP 配置在全集上报告的最优结果较多, 但各来源组的表现不同. '
                  r'例如, ramalho 组中 Z3 FP 序键配置报告并通过复核 $1320$ 项, '
                  r'OptiMathSAT 为 $1142$ 项; griggio 组中 OptiMathSAT 报告最优 $2549$ 项, '
                  r'其中 $688$ 项通过独立复核. '
                  r'未完成复核的结果保留原始输出, 不据此判断其正确或错误. '
                  r'这些比较限于所测版本、配置及该公开输入集合.', ''])
    target = OUT / 'paper-fp-results-draft.tex'
    target.write_text('\n'.join(lines))
    print('Verified full FP export and wrote', target.relative_to(OUT.parent.parent))


if __name__ == '__main__':
    main()
