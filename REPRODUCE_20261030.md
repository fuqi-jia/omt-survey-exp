# 2026-10-30：Z3 5.3.3 更新

本轮重跑Z3的97个性能实例、40个大系数实例、6个病态约束规模及6个非线性实例，并对全部1120个公开浮点实例重新执行三条路线及结果核验。其他求解器的性能与数值诊断沿用已完成的批次；逐行来源记录在各运行目录的`cohort-provenance.json`中。

## 环境与命令

在既有实验依赖环境中使用`z3-solver==5.3.3.0`，确认Python接口与命令行程序均报告5.3.3。官方wheel的地址、SHA-256和本次安装路径见`runs/toolchain_20261030/z3-installation.json`。

```bash
python -c 'import z3; print(z3.get_version_string())'
z3 -version
python scripts/paper_refresh_20261028.py --solvers z3 --workers 6 --cores 0,2,4,6,8,10 --output runs/paper_refresh_20261030
python scripts/diagnostics_refresh_20261028.py --kind exact --solvers z3 --timeout 120 --output runs/exact_refresh_20261030
python scripts/diagnostics_refresh_20261028.py --kind illcond --solvers z3 --timeout 120 --output runs/illcond_refresh_20261030
python scripts/nra_refresh_20261028.py --solver z3 --timeout 120 --output runs/nra_20261030
```

性能调用继续采用600秒、4GB、单线程，数值诊断采用120秒。性能输入清单及其SHA-256与上一批次相同。运行目录保留其他求解器的已完成记录，脚本只执行指定的Z3单元。

## 公开浮点全量实验

```bash
python scripts/public_fp_full_20261030.py --workers 64
```

输入仍为`o300`集合的全部1120个实例；三条路线合计3360项优化任务，求解与逐项核验预算沿用上一批次。原生FP路线使用OptiMathSAT 1.7.4，目标编码及结果核验使用Z3 5.3.3。运行环境为Intel Xeon Platinum 8153，原始输出随结果一并归档。

## 汇总与检查

```bash
python scripts/summarize_refresh_20261028.py --output runs/paper_refresh_20261030 --require-complete
python scripts/audit_refresh_20261030.py
```

汇总入口为`RESULTS_FOR_PAPER.md`，完整性记录为`runs/toolchain_20261030/delivery-audit.json`。历史运行目录继续保留。
