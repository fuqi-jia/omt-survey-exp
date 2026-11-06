# 600 秒本地数值与非线性实验

本轮将原先限时 120 秒的大系数背包、Hilbert 线性系统和全部非线性实验重新运行至 600 秒。硬件为本地 Intel Core i7-11700F、32 GB 内存，每次调用单线程、4 GB 内存上限。未在远程服务器启动本轮实验。此前已完成的 600 秒性能、CGM MaxSMT 和浮点实验保留原始记录。

## 数据范围

结果目录为 `runs/uniform600_20261106/`，旧目录保持原样。

- `exact/`：40 个背包实例 × 9 个配置，共 360 次调用。
- `illcond/`：6 个规模 × 7 个配置，共 42 次调用。
- `nra_base/`、`nra_extensions/`：6 个单变量算例及对应初值，共 46 次调用。
- `nra_public/`：43 个 MINLPLib 实例 × 7 个配置，共 301 次调用。
- `nra_disjunctive/`：9 个析取实例 × 5 个配置，共 45 次调用。
- `nra_irrational/`：9 个无理最优值算例，含局部方法的两组初值，共 69 次调用。

合计 863 次主实验调用；`diagnostics/` 另保留严格约束例与 A5 的两次 OptiMathSAT 原生 API 状态查询，限时同为 600 秒。多变量模型逐字节复制自原始已选定模型，未改变问题集、初值、可行性标准或目标误差标准。`instance_manifest.json` 和各组 `protocol.json` 记录输入映射与哈希。`source-snapshots/` 保留执行代码；`launch/`、`workers/`、`workers_extra/` 和各求解器目录保留调用、原始输出与结果。两个本地队列以原子任务声明避免重复求解，重复领取的调度记录不计为新求解。两个队列最初有三个逻辑核重叠，随后改为覆盖全部逻辑核且互不重叠的分配；初始映射、修正时间与三个在途任务的迁移保存在 `affinity-policy.json` 和 `affinity-adjustments.json`，各查询的原始 600 秒墙钟截止时间不变。

## 运行入口

Python 依赖和求解器版本与正文保持一致。Z3 CLI 必须为 5.3.3，并将同版本 Python 包放在模块搜索路径前部。IPOPT、Couenne 的共享库目录应位于动态库搜索路径中；CBC 与精确 SCIP 分别通过 `CBC_BIN`、`SCIP_EXACT` 指定。

```bash
export OMT_UNIFORM600_OUTPUT=runs/uniform600_reproduction
python scripts/uniform600_20261106.py prepare
python scripts/uniform600_20261106.py batch --exclude-gurobi --cores 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
python scripts/uniform600_20261106.py worker --kind numeric --solver highs --core 0
```

复跑使用新的 `OMT_UNIFORM600_OUTPUT` 目录，归档目录的任务声明用于恢复原运行。商业环境应设置同名变量指向同一输出目录。

数值配置依次为 `z3,optimathsat,cpsat,cbc,highs,scip,scip-exact,gurobi,cplex`，其中 `cpsat`、`scip-exact` 仅运行背包组。Gurobi 非线性组使用完整授权的 `milp` Python 环境，分别运行 `worker --kind public|disjunctive|irrational|base --solver gurobi --core ...`。CPLEX 保留作者确认的完整授权 22.1.0；本轮 Gurobi 为 13.0.3。各启动命令在 `numeric_launch.json`、`nra_launch.json`、`nra_extra_launch.json` 中逐项保存。

辅助原生状态查询使用 `scripts/optimathsat_state600_20261106.py`。按官方 SDK 的 `tools/optimathsat-1.7.4-linux-64-bit/python/README.txt` 编译对应解释器的绑定，并将绑定产物与 SDK 的 `python/` 目录加入模块搜索路径。本机使用 Python 3.9，绑定目录为 `/tmp/gomt-optimathsat-api-20261103/lib`。

## 候选采集与核验

每次优化限时 600 秒。SMT 进程在限时内返回后解析其模型；超时记录保留部分标准输出，候选向量为空。数值后端采集本次调用最终提供的接口模型或解文件向量，再按原始约束及既定误差重算。没有因参考值而重新优化。接口缺失向量时，在求解器返回值附近发起独立可满足性查询，该查询另限时 600 秒。原始状态与候选质量分别保留。

若 Couenne 异常退出但已写出解文件，沿用既有解文件读取规则：重建的 NL 必须与实际输入逐字节一致，随后依据列映射读取求解器写出的向量。原始退出状态、错误输出与重算结果均保留，不修改候选点。

完成后执行 `audit_uniform600_20261106.py` 及三组既有 NRA 审计脚本；`delivery-audit.json` 记录矩阵完整性、输入哈希、600 秒设置和候选重算结果。表格数据由审计结果生成。
