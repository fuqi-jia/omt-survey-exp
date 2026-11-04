# 2026-10-29 数值实验：统一 120 秒

大系数背包、病态约束及非线性实数实验均已按 120 秒重新运行，分别完成 360、42、32 次调用。数据、规模、种子、编码和求解器版本沿用前一批次；所有表格结果不变。性能与公开浮点继续采用完整的 2026-10-28 批次，命令见 [REPRODUCE_20261028.md](REPRODUCE_20261028.md)。

## 开源求解器

使用已配置的科学计算 Python 环境，确保 Z3、CBC 与精确 SCIP 的二进制路径可用：

```bash
export CBC_BIN=/path/to/cbc
export SCIP_EXACT=/path/to/scip
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python scripts/diagnostics_refresh_20261028.py --kind exact --timeout 120 --output runs/exact_refresh_20261029
python scripts/diagnostics_refresh_20261028.py --kind illcond --timeout 120 --output runs/illcond_refresh_20261029
python scripts/nra_refresh_20261028.py --timeout 120 --output runs/nra_20261029
python scripts/scipy_refresh_20261029.py --timeout 120 --output runs/nra_20261029
```

SLSQP 的八次比较由一个限时 120 秒的独立进程执行，本次总耗时不足 2 秒。符号求解器逐次限时 120 秒；SCIP 精确模式和其余数值诊断同样采用 120 秒。

## 商业求解器

在完整授权的 `milp` 环境中运行 Gurobi 13.0.3 与 CPLEX 22.1.0：

```powershell
python scripts/diagnostics_refresh_20261028.py --commercial --kind exact --timeout 120 --output runs/exact_refresh_20261029
python scripts/diagnostics_refresh_20261028.py --commercial --kind illcond --timeout 120 --output runs/illcond_refresh_20261029
python scripts/nra_refresh_20261028.py --gurobi --timeout 120 --output runs/nra_20261029
```

## 完整性检查

```bash
python scripts/audit_refresh_20261029.py
```

新数据位于 `runs/exact_refresh_20261029/`、`runs/illcond_refresh_20261029/` 和 `runs/nra_20261029/`。每次诊断保留命令、原始输出及退出状态；完整性记录为 `runs/toolchain_20261029/delivery-audit.json`。此前批次完整保留。
