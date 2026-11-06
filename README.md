# OMT 综述实验材料

本仓库仅保留当前论文第6节使用的基准、结果、原始记录及复现代码。论文：[GOMT](https://github.com/fuqi-jia/GOMT)。论文表格入口为 [`paper/`](paper/)，逐次结果入口为 [`results/`](results/)。

## 目录

| 目录 | 内容 |
| --- | --- |
| `benchmarks/` | 实际输入、参数化实例、公开数据集选取清单和参考解 |
| `results/` | 各实验的逐次结果 `results.csv` 与完整原始记录 `records.tar.gz` |
| `paper/tables/` | 表5—12的CSV及LaTeX表格；表10的两个部分分别导出CSV |
| `paper/figures/` | 累计耗时图、44个绘图数据点及其来源说明 |
| `paper/index.json` | 论文版本、表格标签、实验数量及数据对应关系 |
| `provenance/` | 原路径到现路径的散列清单、实际执行环境与配置记录 |
| `reproduction/` | 实际使用的生成器、编码器、求解接口和核验代码 |
| `scripts/` | 数据完整性检查与独立复现目录准备工具 |

## 论文与实验对应

| 论文位置 | 结果目录 | 实例与调用 |
| --- | --- | --- |
| 表5、表6、累计耗时图 | `results/performance/` | 97个实例，993次调用；含正文使用的40次凸包编码补充调用 |
| 表7：大系数背包 | `results/large-coefficients/` | 40个实例，9个配置，360次调用 |
| 表8：希尔伯特系统 | `results/hilbert/` | 6个规模，7个配置，42次调用 |
| 表9：单变量非线性 | `results/nonlinear/single-variable/` | 6个算例，含两组初值，共46次调用 |
| 表10(a)：公开非凸实例 | `results/nonlinear/public/` | MINLPLib的43例，7个配置，301次调用 |
| 表10(a)：析取非线性 | `results/nonlinear/disjunctive/` | 9个实例，5个配置，45次调用 |
| 表10(b)：无理最优值 | `results/nonlinear/irrational/` | 9个实例，含局部方法初值对照，共69次调用 |
| 正文OptiMathSAT状态观察 | `results/nonlinear/optimathsat-api/` | 严格约束例与A5的2次原生API查询 |
| 表11：公开MaxSMT | `results/maxsmt/` | CGM的1199例，4个配置，4796次调用 |
| 表12：公开浮点与位向量 | `results/floating-point/` | `o300`全部1120例，3条路线，3360次优化任务 |

合计10012次主实验调用及2次辅助API查询。所有正式结果的求解限时为600秒；本次整理没有重新运行优化器。

## 查找一项结果

`results.csv`每行的`record`列指向原始文件，格式为`压缩包路径#包内路径`。例如：

```text
results/maxsmt/records.tar.gz#cgm-n002-p06-i001/z3-maxres/result.json
```

压缩包内同时保留调用命令、原始状态、输出、模型或解文件及核验记录。非线性结果的`native_status`、`status`、`feasible`和`reference_hit`分别保留，不相互替代。浮点结果中的`paper_completed`要求可达性查询为SAT、严格改进查询为UNSAT。

```bash
tar -xOf results/maxsmt/records.tar.gz \
  cgm-n002-p06-i001/z3-maxres/result.json
```

原始记录中的历史绝对路径保持原样；[`provenance/paths.csv.gz`](provenance/paths.csv.gz)将每个保留文件映射到现有压缩包及成员，并保存原始SHA-256。压缩归档不改变其内容。

## 校验与复现

```bash
python scripts/validate.py           # 输入、散列、调用矩阵、表格和绘图统计
python scripts/validate.py --deep    # 另核对NRA候选/参考值及完整FP核验协议
python scripts/reproduce.py --study nonlinear --workspace /tmp/omt-reproduction
```

基础校验只用Python标准库；深度校验需要`requirements.txt`中的科学计算依赖。校验会重新生成表格CSV及`paper/validation.json`，不会重新求解实验。复现准备工具仅生成独立工作目录、输入和命令清单；执行方式见[`reproduction/README.md`](reproduction/README.md)。

公开数据来源、目标语义、计时与候选采集规则见[`PROTOCOL.md`](PROTOCOL.md)。已清理的旧批次可通过Git历史及既有固定标签查阅；当前目录不再保留旧30秒、120秒批次、试跑、页面预览或调度临时文件。
