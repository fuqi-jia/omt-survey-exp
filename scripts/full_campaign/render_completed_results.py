#!/usr/bin/env python3
"""Render the three complete suites after checking their full exported records."""
import collections
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

from summarize import group, statistics_for

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
CONFIGS = {
    'bv': ['oms_bv', 'z3_bv'],
    'bv_lia': ['oms_lia', 'z3_lia'],
    'maxsmt': ['oms_maxres', 'oms_omt', 'z3_maxres', 'z3_wmax'],
}
LABELS = {
    'oms_bv': 'OptiMathSAT', 'z3_bv': 'Z3',
    'oms_lia': 'OptiMathSAT', 'z3_lia': 'Z3',
    'oms_maxres': 'OptiMathSAT MaxRes', 'oms_omt': 'OptiMathSAT OMT',
    'z3_maxres': 'Z3 MaxRes', 'z3_wmax': 'Z3 WMax',
}
TIME_FIELDS = {'par2_s', 'median_with_unsolved_infinity', 'solved_median_s',
               'solved_min_s', 'solved_max_s'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_statistics(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in actual.items():
        if isinstance(value, float):
            # Python versions can differ in the last bit of a float sum.
            # Counts, outcomes, input identities and archive hashes stay exact.
            assert math.isclose(value, expected[key], rel_tol=1e-12, abs_tol=1e-9), key
        else:
            assert value == expected[key], key


def load_complete(suite):
    report = json.loads((OUT / (suite + '-complete.json')).read_text())
    coverage = report['coverage']
    assert report['suite'] == suite and report['completed_suite_only']
    assert coverage['all_inputs_completed']
    assert not any(coverage[k] for k in ['errors', 'objective_disagreements',
                                       'missing_inputs', 'duplicate_inputs'])
    manifest_bytes = (ROOT / 'benchmarks/full_public/manifests' / (suite + '.jsonl')).read_bytes()
    assert sha(manifest_bytes) == report['manifest_sha256']
    entries = [json.loads(line) for line in manifest_bytes.splitlines()]
    manifest = {entry['id']: entry for entry in entries}
    assert len(manifest) == len(entries) == report['planned_inputs']
    packed = (OUT / (suite + '-results.csv.gz')).read_bytes()
    assert sha(packed) == report['results_gzip_sha256']
    raw = gzip.decompress(packed)
    assert sha(raw) == report['results_csv_sha256']
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    assert len(rows) == report['solver_runs'] == len(manifest) * len(CONFIGS[suite])
    pairs = {(row['case'], row['variant']) for row in rows}
    assert len(pairs) == len(rows)
    assert pairs == {(case, variant) for case in manifest for variant in CONFIGS[suite]}
    for row in rows:
        source = manifest[row['case']]
        assert row['sha256'] == source['sha256'] and row['path'] == source['path']
    cases = collections.defaultdict(list)
    cells = collections.defaultdict(list)
    for row in rows:
        cases[row['case']].append(row)
        cells[group(suite, row['path']), row['variant']].append(row)
    for observations in cases.values():
        assert len({row['run'] for row in observations}) == 1
        assert len({row['host'] for row in observations}) == 1
    archives = json.loads((OUT / (suite + '-archives.json')).read_text())
    assert archives == report['archives']
    hosts = collections.Counter(observations[0]['host'] for observations in cases.values())
    assert len({item['host'] for item in archives}) == len(archives)
    assert {item['host']: item['runs'] for item in archives} == dict(hosts)

    def stats(observations):
        result = statistics_for(observations)
        if suite == 'bv_lia':
            result = {key: value for key, value in result.items() if key not in TIME_FIELDS}
        return result

    for variant in CONFIGS[suite]:
        same_statistics(stats([row for row in rows if row['variant'] == variant]), report['overall'][variant])
    expected_groups = [dict(group=g, variant=v, **stats(observations))
                       for (g, v), observations in sorted(cells.items())]
    assert len(expected_groups) == len(report['by_group'])
    for actual, expected in zip(expected_groups, report['by_group']):
        same_statistics(actual, expected)
    return report


def table(lines, headers, rows):
    lines.extend(['', '| ' + ' | '.join(headers) + ' |',
                  '| ' + ' | '.join(['---'] * len(headers)) + ' |'])
    lines.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows)
    lines.append('')


def main():
    reports = {suite: load_complete(suite) for suite in CONFIGS}
    lines = [
        '# 已完成的公开基准结果', '',
        '本报告覆盖 BV、整数伴随诊断与 MaxSMT 的完整输入集合。FP 不纳入本报告；'
        'FP 全集完成并通过归档审计后，另行生成四组总汇总。', '',
        '所有输入均实际调用相应配置，超时、内存不足、未定和原始无效输入全部保留。'
        '“完成运行”不等于求得最优解。', '',
        '求解器为 OptiMathSAT 1.7.4 和 Z3 4.15.4；单线程、每次 600 秒、8 GiB 地址空间上限。'
        '同一输入的各配置在同一节点运行。独立复核使用 Z3 分别检查目标值可达和无严格改进，'
        '每条查询 60 秒，时间另计。复核通过数量是报告最优数量的子集。'
        'PAR-2 以全部语法有效输入为分母，未完成判定者计 1,200 秒。',
    ]
    table(lines, ['集合', '全部输入', '配置数', '全部观测', '原始归档数'], [
        [suite, report['planned_inputs'], len(CONFIGS[suite]), report['solver_runs'], len(report['archives'])]
        for suite, report in reports.items()])
    for suite, title in [('bv', '原生 BV'), ('maxsmt', 'MaxSMT(LIA)')]:
        report = reports[suite]
        lines.extend(['## ' + title, ''])
        if suite == 'bv':
            lines.append('公开包全部 254 项均语法有效。该集合包含公开的构造实例，不等同于原论文的非公开工业实例全集。')
        else:
            lines.append('公开 release 的全部 2,264 项均已运行，其中 2,245 项语法有效。'
                         '19 项错误或截断已存在于原始发布包，按实际响应单列。'
                         '该 release 不包含原论文的全部基准家族。')
        rows = []
        for variant in CONFIGS[suite]:
            stats = report['overall'][variant]
            outcomes = stats['outcomes']
            rows.append([LABELS[variant], stats['claimed_optimal'], stats['independently_verified'],
                         outcomes.get('timeout', 0), outcomes.get('oom', 0), outcomes.get('unknown', 0),
                         outcomes.get('invalid_input', 0), f"{stats['par2_s']:.2f}"])
        table(lines, ['配置', '报告最优', '独立复核', '超时', '内存不足', '未定', '无效输入', 'PAR-2 / 秒'], rows)
        cells = {(item['group'], item['variant']): item for item in report['by_group']}
        groups = {item['group'] for item in report['by_group']}
        if suite == 'maxsmt':
            groups = sorted(groups, key=lambda g: (int(g.split('/')[0]), g.split('/')[1]))
        else:
            groups = sorted(groups, key=lambda g: (g == 'hd', int(g.split('_')[1]) if g != 'hd' else 0))
        rows = []
        for name in groups:
            first = cells[name, CONFIGS[suite][0]]
            rows.append([name, f"{first['valid_inputs']}/{first['source_inputs']}"] +
                        [f"{cells[name, variant]['claimed_optimal']}/{cells[name, variant]['independently_verified']}"
                         for variant in CONFIGS[suite]])
        lines.append('以下保留全部来源组；求解器列为“报告最优 / 其中独立复核通过”。')
        table(lines, ['来源组', '有效 / 发布'] + [LABELS[v] for v in CONFIGS[suite]], rows)
        if suite == 'maxsmt':
            lines.append('组名中的数字为软约束比例（%），`unw`、`w` 分别为无权、有权设置。')
        lines.extend(['', '共同报告最优的结果未发现目标值冲突；未完成复核不等于结果错误。', '',
                      f'[完整记录]({suite}-results.csv.gz) · [覆盖与统计]({suite}-complete.json) · '
                      f'[原始归档索引]({suite}-archives.json)', ''])
    lia = reports['bv_lia']
    lines.extend(['## 整数伴随文件的语义诊断', '',
                  '原包全部 254 个整数文件保留原始约束和目标顺序，两个工具均显式采用词典序。'
                  'SAT 或输出无穷界不在本组中升级为最优模型保证；本组不作 BV/LIA 等价编码的性能排名。'])
    table(lines, ['配置', '返回 SAT', '报告无穷界', '超时', '原生内存分配失败'], [
        [LABELS[v]] + [lia['overall'][v]['outcomes'].get(k, 0)
                       for k in ['diagnostic_sat', 'diagnostic_unbounded', 'timeout', 'oom']]
        for v in CONFIGS['bv_lia']])
    lines.extend([
        '11 项原生内存分配失败已逐项核对原始 `std::bad_alloc` 响应；CSV 同时保留原始状态与复核分类。'
        '7 项输入暂存故障仅在修复基础设施后重试，未启动求解器的初次尝试另行保留。', '',
        '[完整记录](bv_lia-results.csv.gz) · [覆盖与统计](bv_lia-complete.json) · '
        '[原始归档索引](bv_lia-archives.json) · [故障与重试证据](staging-incident/README.md)', '',
        '## 原始证据与主稿表格', '',
        '下列压缩包均已在控制节点完成逐文件核验；本报告的生成过程另核对全部 CSV 观测、'
        '输入清单哈希、配置组合、来源组统计及归档覆盖。D 盘回传情况以相应 '
        '`*-local-archives.json` 的 `local_complete` 为准，不由控制端归档完成状态推断。',
    ])
    table(lines, ['集合', '控制端原始归档 / 字节', 'LaTeX 表格草稿'], [
        [suite, sum(item['bytes'] for item in report['archives']), f'[查看]({draft})']
        for suite, report, draft in [
            ('bv', reports['bv'], 'paper-bv-results-draft.tex'),
            ('bv_lia', reports['bv_lia'], 'paper-lia-diagnostic-draft.tex'),
            ('maxsmt', reports['maxsmt'], 'paper-maxsmt-results-draft.tex'),
        ]])
    lines.extend(['[数据来源、版本与完整方法](README.md) · [主稿方法草稿](paper-methods-draft.tex)', '',
                  '本文件由 `scripts/full_campaign/render_completed_results.py` 从三组完整导出生成。', ''])
    target = OUT / 'completed-results.md'
    target.write_text('\n'.join(lines))
    print('Verified full records and wrote', target.relative_to(ROOT))
    print('Total inputs:', sum(r['planned_inputs'] for r in reports.values()),
          'observations:', sum(r['solver_runs'] for r in reports.values()))


if __name__ == '__main__':
    main()
