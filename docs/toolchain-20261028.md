# 2026-10-28 工具环境

2026-10-29 保持本工具环境，将大系数、病态约束及非线性实数实验统一为 120 秒并全部复跑；当前命令与结果入口见 [REPRODUCE_20261029.md](../REPRODUCE_20261029.md)。

论文重跑使用的实际版本及安装包校验值见 `runs/toolchain_20261028/versions.json`；Python 包记录见同目录的 `linux-python-freeze.txt` 和 `pypi-provenance.json`。

## 科学计算与开源求解器

使用 Python 3.12，安装 `requirements-refresh-20261028.txt`。CBC 2.10.13、MiniZinc 2.10.1（含 Gecode 6.4.0）和 SCIP Optimization Suite 10.1.0 采用官方发布包，下载地址与校验值记录在版本文件中。OptiMathSAT 使用官方 1.7.4 二进制；OCAC 使用论文公开的 1.0.4 实现。

PySCIPOpt 6.3.0 的预编译 wheel 内置 SCIP 10.0.2，因此本轮从源代码链接 SCIP 10.1.0：

```bash
export SCIPOPTDIR="$PWD/tools/scipoptsuite-10.1.0"
export LIBRARY_PATH="$SCIPOPTDIR/lib64"
python -m pip install --no-binary=pyscipopt pyscipopt==6.3.0
python -c 'from pyscipopt import Model; m=Model(); print(m.getMajorVersion(),m.getMinorVersion(),m.getTechVersion())'
```

计时运行不设置全局 `LD_LIBRARY_PATH`，各求解器使用自己的运行库。数值诊断每次在独立解释器中加载一个求解器。

```bash
export CBC_BIN="$PWD/tools/cbc/bin/cbc"
export SCIP_EXACT="$SCIPOPTDIR/bin/scip"
export PATH="$PWD/.venv/bin:$PWD/tools/cbc/bin:$PWD/tools/minizinc/bin:$PATH"
python scripts/paper_refresh_20261028.py --workers 6 --cores 0,2,4,6,8,10
python scripts/diagnostics_refresh_20261028.py --kind exact
python scripts/diagnostics_refresh_20261028.py --kind illcond
python scripts/nra_refresh_20261028.py --numeric
python scripts/summarize_refresh_20261028.py --require-complete
```

主性能表保持同一生成器、规模与种子。商业线性模型通过原生接口建立，并从求解调用开始计时；调度大 M 模型继续使用 Pyomo.GDP，指示约束继续使用原生接口。每次调用单线程、600 秒、4 GB。开源与商业命令见 `REPRODUCE_20261028.md`；同时运行时分别指定 CPU 核。

## 公开浮点全量结果

`runs/public_fp_full_20261028/` 保存全部 1120 个实例的结果、核验状态及原始日志压缩包。`selection-full.json` 给出输入清单和校验值；`delivery.json` 给出结果压缩包与运行脚本校验值。原始输入通过 `scripts/fetch_public_fp_full.py` 从固定的公开数据层生成。

ESBMC 输入中的旧式带反斜杠符号在送入 Z3 前进行一一重命名，原始文件不变。不可满足与 NaN 单独统计；NaN 不计为数值最优结果。
