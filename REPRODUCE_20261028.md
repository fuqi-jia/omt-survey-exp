# 2026-10-28 论文实验重跑

数值诊断已在 2026-10-29 统一为 120 秒并全部重跑，当前数值结果和命令见 [REPRODUCE_20261029.md](REPRODUCE_20261029.md)。本文件保留性能及公开浮点批次的复现入口。

性能基准为四个线性族 57 个实例及作业车间 40 个实例，种子、规模、编码与当前论文相同。原有 `configs/full.yaml` 和归档数据保持不变。

## Gurobi 与 CPLEX

使用 Python 3.10–3.14、Gurobi 13.0.3，以及已安装并授权的 CPLEX 22.1.0。建模依赖：

```powershell
python -m pip install gurobipy==13.0.3 pulp==3.3.2 pyomo==6.10.1 pyyaml psutil
$env:GRB_LICENSE_FILE = "E:\softwares\gurobi\13.0.0\win64\bin\gurobi.lic"
python scripts/paper_refresh_20261028.py --commercial --workers 1
python scripts/diagnostics_refresh_20261028.py --commercial --kind exact --timeout 60 --output runs/exact_refresh_20261028
python scripts/diagnostics_refresh_20261028.py --commercial --kind illcond --timeout 60 --output runs/illcond_refresh_20261028
python scripts/nra_refresh_20261028.py --gurobi --timeout 60 --output runs/nra_20261028
```

CPLEX 接口使用完整授权环境中的安装，不要让其他 Python 环境覆盖该接口。性能运行共 274 次调用：线性族各用 Gurobi、CPLEX；调度各用两者的大 M 与指示约束编码。每次单线程、600 秒、4 GB 内存上限；脚本按单元保存结果，中断后执行相同命令即可续跑。

结果保存在 `runs/paper_refresh_20261028/cells/`、`runs/exact_refresh_20261028/results-commercial.json`、`runs/illcond_refresh_20261028/results-commercial.json` 和 `runs/nra_20261028/gurobi.json`。数值诊断的当前入口见 2026-10-29 的复现记录。

## 其他实验

开源性能调用为 719 次，使用同一性能清单；结果写入 `runs/paper_refresh_20261028/`。公开浮点使用完整 o300 集合的 1120 个原始实例及三条路线，共 3360 次优化任务，在实验室服务器运行。

```bash
python scripts/fetch_public_fp_full.py
python scripts/public_fp_full.py --workers 16
```

`selection-full.json` 记录全部输入及校验值；不存在 20 个实例抽样。原始输入和派生编码可重新生成，结果及核验记录保存在对应运行目录。

## 完整性检查

```bash
python scripts/summarize_refresh_20261028.py --require-complete
python scripts/audit_refresh_20261028.py
```

本批次 993 次性能调用、3360 次公开浮点优化及全部数值诊断均已完成。汇总为 `RESULTS_FOR_PAPER.md`，数据来源记录为 `DATA_PROVENANCE.md`。
