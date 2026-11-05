# 公开浮点与位向量基准：600秒结果

全部1120个原始实例的三条路线均已运行，3360项记录完整；逐项检查通过。

| 路线 | 通过可达性与最优性核验 |
|---|---:|
| OptiMathSAT原生浮点 | 773/1120 |
| Z3浮点约束与位向量目标 | 774/1120 |
| Z3纯位向量转换 | 383/1120 |

求解、编码准备与单项核验预算均为600秒。两台Xeon Platinum 8153机器各128个物理核心，单次调用单线程、4 GiB地址空间上限；分组按原清单偶数、奇数索引确定。Z3 5.3.3与OptiMathSAT 1.7.4的二进制在两台机器上一致。

- `cases/`：1120项逐例记录，每例包含三条路线。
- `raw-logs.tar.gz`：原始进程输出、状态、准备和核验记录，按实例索引与路线定位。
- `results.csv`、`table-rows.tex`：3360项对应关系与论文表12数据行。
- `audit.json`：预算、状态、原始输入散列值与跨路线目标值核对；4例NaN、39例零最优值，各已完成路线的零符号一致。
- `environment.json`、`shard-manifest.json`、`delivery.json`：环境、分组及完整性记录。
- `shards/`：两组原始交付包；`resumed-completed-routes.json`记录本次600秒启动阶段续用的113项已结束调用。原30秒批次未参与统计。

复现与核对命令见仓库根目录的 `REPRODUCE_FP_20261106.md`。原始输入为 `benchmarks/public_fp/original-fp-inputs-20261104.tar.gz`，输入清单为 `selection-full.json`；派生编码和核验输入由所存运行脚本重建。
