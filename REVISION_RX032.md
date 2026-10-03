# rx032 修订实验说明（2026-10-04）

工作目录已迁移到 `D:\D_Work\ISCAS\paper\jos2026\omt-survey-exp`。本目录仍是独立 Git 仓库；原始结果和历史来源未改写。此说明补充 `DATA_PROVENANCE.md`，按当前 LaTeX 表格整理实际实验条件。

## 主表来源及预算

| LaTeX 表格标签 | 数据 / 程序 | 环境与实际预算 |
|---|---|---|
| `tab:exp-sep` | `runs/long600/results.json`；`configs/long600.yaml` | WSL Ubuntu 24.04，600 秒、单线程、4 GB 地址空间上限，种子 0/1/2。仅 Gurobi GAP 160/320 共六条记录由同机 Windows 补跑替代，来源 `runs/long600/gurobi_win/`，600 秒、单线程，未施加 Linux 地址空间上限。 |
| `tab:exp-jobshop` | `runs/jobshop_seeds/results.json` | 同上 WSL 条件，规模 7–10、种子 0–9；种子 0–2 复用同实例 `long600` 记录。来源字段和历史重跑说明保留。 |
| `tab:exp-spread` | `runs/rx032_audit/seed-distributions.csv` | 重新汇总历史种子记录，没有重跑或挑选成功种子。中位数将未证最优者排序为正无穷；四分位区间仅对全部证最优的组报告，采用 inclusive 线性插值。成功耗时范围明确为条件统计。 |
| `tab:exp-exact` | `runs/exact/`；`scripts/exact_experiment.py` | WSL 数值诊断；Z3/OptiMathSAT 子进程 60 秒，精确 SCIP 外层 120 秒。其他 API 无统一墙钟限时；CPLEX 显式一线程，其他参数按脚本。不得套用主表统一 600 秒/4 GB/单线程。 |
| `tab:exp-illcond` | `runs/illcond/`；`scripts/illcond_experiment.py` | WSL 数值诊断；Z3/OptiMathSAT 子进程 60 秒，其余 API 未统一设置墙钟预算。 |
| `tab:exp-nra` | `runs/nra/`；`scripts/nra_experiment.py` | 前四行 OptiMathSAT 30 秒、OCAC 60 秒；后两行两者均 60 秒。SciPy 为 SLSQP 默认停止条件，Gurobi 为 NonConvex=2，无统一墙钟时限。后两行所测 OCAC 构建用 `(minimize (+ x 0))`；裸变量目标日志仍保留。 |
| `tab:exp-public-fp` | `runs/rx032_public/` | 本轮新增公开 FP/BV 诊断，详见下节。 |

Windows 合并按许可证限制预先确定，不取跨平台最快值。亚秒级主表时间及跨平台格不用于细微速度排序。各历史诊断的未设置参数沿用各工具默认值，不追认统一配置。

## 调度规约与历史数据核验

```bash
.venv/bin/python scripts/revision_audit.py
```

结果见 `runs/rx032_audit/audit.json`：

- 97 个主实验实例，所有已证明最优的目标值一致。
- 40 个作业车间实例按原种子重新生成，与保存的 SMT/MiniZinc 输入一致；报告保存输入和结果文件哈希。
- 各时间变量为有界非负整数。令 H 为全部工时之和：SMT 直接限制工序结束不超过 H；MILP/MiniZinc 利用 `Cmax ≤ H`；CP-SAT 对结束变量给出界。
- Pyomo.GDP 根据显式开始变量 `[0,H]` 界生成的自动 M 为 **H+d_i**。结合完整完工约束，人工取 H 足够，但自动转换未使用这一隐含紧界。另有 PuLP 编码使用 H，不是本表 GDP 列的来源。
- 目标值交叉一致只是辅助核验；一般编码等价性依靠模型解释，不能由有限样本代替证明。

## 新增公开 FP / FP+BV / BV 诊断

来源为 [Trentin 与 Sebastiani，JAR 2021](https://doi.org/10.1007/s10817-021-09600-4) 的公开实验工件。原生文件保留原始 `:source`、类别与约束；不把所有来源均称为工业实例。

工件固定为 `patricktrentin88/jar2020_floatingpoint_test:1.0`，镜像 digest 与数据层 SHA-256 记录在 `benchmarks/public_fp/source.json`。只获取约 89 MB 的数据层，不运行容器，也不执行工件里的管理脚本。

从工件 `o300` 的 1120 个原生优化文件，按五个来源组 × 两个优化方向分为十层；计算 `SHA256("rx032-public-v1:" + 原始成员路径)`，每层取哈希最小的两个文件。完整选择规则、候选数量、文件名与哈希见 `selection.json`。选择先于运行，所有 20 个实例均计入分母。

三种形式：

1. `fp`：未经修改的原生优化文件，OptiMathSAT 1.7.4。
2. `bvfp`：原有 FP 约束，加非 NaN 条件与单调无符号 BV 序键，用 Z3 4.15.4 优化该键。
3. `bv`：对第 2 种约束经 `simplify / fpa2bv / simplify` 变换后，再用 Z3 优化同一 BV 键。

序键将负数 IEEE 位串逐位取反，将非负数符号位翻转。它保留非 NaN 数值次序，并把数值相等的 −0 和 +0 细化为 −0 < +0。原生输入不附加非 NaN 约束；派生编码的域与零值细化均明确记录。工件自带的 `fp_to_bv` 文件作为来源材料一并取出，但**没有用于本轮结果**；本轮派生编码由公开的修订脚本产生，避免依赖不透明的目标变换约定。

运行资源：同一 AMD Ryzen 9 7940HS 主机的 WSL/Linux；每进程 RLIMIT_AS=4 GiB；顺序调用，Z3 禁用并行。OptiMathSAT 外层 30 秒，Z3 内部 30 秒并设 35 秒进程保护；编码准备单独 35 秒。候选最优值额外进行两次原始 FP 约束查询：值可达应为 SAT，严格更优应为 UNSAT；每次内部 30 秒，共同外层 65 秒。所有核验使用 Z3，因此属于另外的查询检查，不是跨实现证明或经检查的证明证书。

| 结果 | 原生 FP | FP+BV | 纯 BV |
|---|---:|---:|---:|
| 已核验最优 | 12 | 12 | 7 |
| 候选值，但核验未完成 | 2 | 2 | 0 |
| 求解超时 | 6 | 6 | 10 |
| 求解内存不足 | 0 | 0 | 3 |
| 总数 | 20 | 20 | 20 |

所有双查询核验成功的同实例跨编码结果，在浮点数值意义上相同，共 10 个有多种已核验形式的实例。编码回归检查还穷举小格式 FP(3,4) 的 114 个非 NaN 值，共 12,996 对比较，核验次序映射与零值细化，并检查 Z3 BV 目标按无符号数优化。详见 `encoding-check.json`。

本实验有 20 个独立输入、60 个实例—编码组合；纯 BV 不是独立采集的原生 BV 工业总体。30 秒诊断不能重现原论文的 600 秒性能实验；不同列还同时改变编码与实现，不从成功数推出总体快慢排名。超时或核验超时不是错误结果的证据。

### 复现

Python 环境需要 `z3-solver==4.15.4.0`，原生工具放在 `tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat`。本机使用 `/home/fuqi/anaconda3/envs/omt/bin/python`。下载和选择仅用 Python 标准库：

```bash
python3 scripts/fetch_revision_public_fp.py
python scripts/revision_public_fp.py
python3 scripts/summarize_revision_public.py
python scripts/check_revision_semantics.py
```

运行器跳过已有结果，避免把复现命令当作性能择优重跑。需要新实验时应另定结果位置和实验配置，不能覆盖本次记录；这只涉及小型结果目录，不复制任何编译树。派生 SMT 输入可重建，归档哈希位于 `summary.csv`；单个纯 BV 文件超过 100 MB，因此不纳入 Git，但在 D 盘当前结果目录保留。

### 解析修复的记录

首轮适配器只识别 `(_ FloatingPoint e s)`，未覆盖最后两组的 `Float32/Float64` 别名。补跑仅修复类型解析失败造成的派生条目与原生结果核验，不重跑已完成的原生求解，也不重新选择样本。首轮脚本、环境记录和失败日志保存在 `runs/rx032_public/adapter-before-sort-fix/`；其他十二个实例的初始结果保持原样。当前环境 JSON 的脚本哈希对应修复后程序，修复前哈希保存在上述归档。

## 存储与迁移

原实验虚拟环境的文本入口已由 Study 路径调整为 Work；该操作只修复本地入口，不修改依赖版本或历史结果。Windows 运行包装器通过 `$PSScriptRoot` 定位仓库。迁移和环境修复清单位于主稿仓库 `../revision/`。

数据层、派生编码和历史原始证据保存在 D 盘；Git 记录固定来源、下载/生成脚本、选择清单、结果、核验日志与哈希。没有复制或新建求解器完整构建树。
