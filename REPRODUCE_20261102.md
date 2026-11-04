# 2026-11-02 非线性扩展复现

本轮新增 360 次正式调用，保留此前全部性能、精确性和公开浮点结果。

| 对照 | 实例/调用 | 数据入口 |
|---|---:|---|
| IPOPT、Couenne 单变量补充 | 8+6 次 | `runs/nra_numeric_extensions_20261102/` |
| MINLPLib 连续非凸二次 | 43×7=301 次 | `runs/nra_public_20261102/` |
| 析取非线性资源分配 | 9×5=45 次 | `runs/nra_disjunctive_20261102/` |

版本为 Z3 5.3.3、OCAC 1.0.4、OptiMathSAT 1.7.4、IPOPT 3.14.20、
Couenne 0.5.9、SciPy 1.18.1、Gurobi 13.0.3。各调用限时 120 秒、
单线程、4 GB。Linux 调用固定到互不重叠的物理核心；Gurobi 使用已授权的
Windows `milp` 环境。原始日志、输入、候选向量、参考值及 SHA-256 随数据保留。
构建说明见 [`docs/toolchain-nra-20261102.md`](docs/toolchain-nra-20261102.md)。

已有单元自动跳过。重新执行整批实验前，应将对应运行目录归档，或在独立副本中
使用空的运行目录；不要覆盖旧日志。

## 输入与参考值

```bash
python3 scripts/fetch_minlplib_qcqp_20261102.py
/tmp/gomt-refresh-venv/bin/python scripts/nra_public_20261102.py --prepare
/tmp/gomt-refresh-venv/bin/python scripts/nra_disjunctive_20261102.py --prepare
```

MINLPLib 的全部 43 个符合条件的实例均纳入，筛选不依赖求解结果。原始元数据
和模型存于 `benchmarks/minlplib-qcqp-20261102/`。公开参考点均通过同一多项式
编码核对。析取实例的全部启用集合被枚举，每个凸二次子问题以有理数计算参考值。

## 正式调用

在 Linux 环境中设置运行库及单线程环境变量：

```bash
export LD_LIBRARY_PATH=/tmp/gomt-nlp-20261102/lib
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

/tmp/gomt-refresh-venv/bin/python scripts/nra_public_20261102.py \
  --solvers z3 ocac optimathsat ipopt scipy --cores 0 2 4 6 8 10
/tmp/gomt-refresh-venv/bin/python scripts/nra_public_20261102.py \
  --solvers couenne --cores 0 2 4 6 8 10

/tmp/gomt-refresh-venv/bin/python scripts/nra_disjunctive_20261102.py \
  --solvers z3 ocac optimathsat --cores 0 2 4 6 8 10
/tmp/gomt-refresh-venv/bin/python scripts/nra_disjunctive_20261102.py \
  --solvers couenne --cores 12

/tmp/gomt-refresh-venv/bin/python scripts/nra_numeric_extensions_20261102.py --solver ipopt --core 14
/tmp/gomt-refresh-venv/bin/python scripts/nra_numeric_extensions_20261102.py --solver couenne --core 14
```

上面各批顺序运行；如并发执行，使用互不重叠的核心。原始六例的 Z3、OCAC、
OptiMathSAT、SciPy 和 Gurobi 对照保留 `runs/nra_20261030/` 的原始记录。

在已授权的 PowerShell `milp` 环境、仓库根目录执行：

```powershell
python scripts/nra_public_gurobi_20261102.py
python scripts/nra_disjunctive_20261102.py --gurobi
```

## 处理与核对

```bash
/tmp/gomt-refresh-venv/bin/python scripts/recover_nra_solution_files_20261102.py
/tmp/gomt-refresh-venv/bin/python scripts/nra_public_20261102.py --summary
/tmp/gomt-refresh-venv/bin/python scripts/audit_nra_public_20261102.py
/tmp/gomt-refresh-venv/bin/python scripts/audit_nra_disjunctive_20261102.py
python3 scripts/render_nra_tables_20261102.py
```

恢复脚本只读取求解器已经写出的 `.sol`，不重新求解或修改向量。异常退出的原
结果保存在 `solver-run.json`；重新生成的 NL 须与原输入逐字节相同，之后按列映射
读取向量并重新检查原约束和目标。完整记录见 `solution-file-recovery.json`。

接受标准为缩放后的最大约束/变量界违反量不超过 `1e-6`，且
`abs(f-f*)/max(1,abs(f*)) <= 1e-6`。OCAC 的接口不提供最优模型时，以其返回值
在原约束中发起独立 Z3 可满足性查询，时限 30 秒，查询不使用参考值。

两项审计分别验证全部 301、45 个单元；表格由 `table.json` 和 `summary.json`
生成。先前六工具运行所用的脚本快照保存在 `source-snapshots/`，后续只修正了
Couenne 的 AMPL 选项命名空间。精确二进制及动态库校验值见 `toolchain.json`。

## Z3 调用与编码复测

作者追问比较结果后，另执行 36 项诊断和一次原输入重复调用，保留在
`runs/nra_z3_check_20261102/`。默认 NLSAT 优化开关为 true；九个简化输入逐条
约束证明与原输入等价。简化编码与去掉最优界检查内部限额的两组优化均完成
2/9，原正式编码为 3/9。4 单元种子 2 的原输入重复调用再次得到精确最优值 52。
已知参考值上的可满足性/严格改进查询单列为诊断，不替代优化调用。正式主表不变。

```bash
/tmp/gomt-refresh-venv/bin/python scripts/check_z3_disjunction_20261102.py
```

两种优化诊断均限时 120 秒；已知参考值的判定查询限时 30 秒。汇总为
`runs/nra_z3_check_20261102/summary.json`，完整参数表为 `z3-parameters.txt`。

## 无理最优值与非凸分支补充

九个预先固定的算例及解析参考值在 `benchmarks/nra-irrational-20261102/`，
结果在 `runs/nra_irrational_20261102/`。五个全局工具各运行全部九例；IPOPT 与
SLSQP 各在 A/B 两类的六例上使用两组初值，共 **69 次正式调用**。

```bash
/tmp/gomt-refresh-venv/bin/python scripts/nra_irrational_20261102.py --prepare
/tmp/gomt-refresh-venv/bin/python scripts/nra_irrational_20261102.py --run
```

在已授权的 PowerShell `milp` 环境中执行：

```powershell
python scripts/nra_irrational_gurobi_20261102.py
```

完成后读取原始输出、核对精确表达式及各返回状态，并生成表格：

```bash
/tmp/gomt-refresh-venv/bin/python scripts/audit_nra_irrational_20261102.py
/tmp/gomt-refresh-venv/bin/python scripts/render_nra_irrational_20261102.py
```

`reference_hit` 记录候选向量在数值容差内是否达到参考值，
`correct_optimal_return` 同时要求原始终止状态正确。Couenne 的 `C_r29_5`
同时给出了可行候选和 `infeasible` 状态；论文列出候选值并说明状态冲突，不据此
判定原模型不可行。三次相同 NL 输入复跑记录见 `couenne-status-recheck.json`，
不计入正式 69 次调用。

## 2026-11-03 异常与语义复核

新增定向诊断不改变上述正式结果，输出保存在 `runs/review_diagnostics_20261103/`：

- OptiMathSAT 的 `C1_inf_unattained` 与 `A_r5` 经同版本 API 重建后均返回
  `MSAT_OPT_SAT_OPTIMAL`，最优值字段分别为 `1+epsilon`、`3+epsilon`，并保留返回模型。
- Couenne 在 `C_r29_5` 中固定 `(x,y)=(1,2)` 后返回 `optimal` 和目标值 5；
  原始 NL 输入及散列一并记录。
- Hilbert `n=10` 的 Gurobi 原始向量、整数恢复向量、精确残差、日志及浮点输入模型
  均已保存；精确枚举覆盖其余 59048 个整数向量。
- 公开 FP 全部 1120 例的结果审计确认 4 个 NaN 状态差异实例和 29 个已认证零目标实例；
  各已完成路线的零符号一致。

执行入口为 `scripts/review_diagnostics_20261103.py`，子命令分别为
`optimathsat`、`couenne`、`hilbert`、`fp`。前两者使用上述 OptiMathSAT/Python
与 Pyomo 环境；Hilbert 在已授权的 Windows `milp` 环境运行；FP 审计只需 Python
标准库读取既有结果。
