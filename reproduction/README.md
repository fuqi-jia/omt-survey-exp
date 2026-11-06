# 复现代码与运行准备

`source.tar.gz`保存本轮实际使用的生成器、编码器、接口及核验器，内容不作重写。文件名中的日期标识执行源码版本；它们不代表仍有多套结果。原始路径与散列见`provenance/paths.csv.gz`。当前调用对应的解释器、二进制、配置和资源记录见`provenance/execution-records.tar.gz`。

## 检查已归档结果

在仓库根目录运行：

```bash
python scripts/validate.py
python scripts/validate.py --deep
```

第一条核对保留对象的原始散列、输入清单、调用矩阵、表5—12的统计及累计图。第二条另在临时目录恢复原始代码与记录，执行五个已有审计入口：数值/NRA完整矩阵、公开NRA、析取NRA、无理最优值和完整FP核验协议。该过程不启动新的优化实验。

## 准备独立复现目录

```bash
python scripts/reproduce.py --study nonlinear \
  --workspace /tmp/omt-nonlinear-reproduction --tools "$PWD/tools"
```

`--study`可取`performance`、`numerical`、`nonlinear`、`maxsmt`、`floating-point`。工具仅展开所需输入与源码，写出`commands.json`，不会运行求解器。目录必须尚不存在。生成的历史执行路径仅存在于这个独立工作目录中。

1. 按根目录`requirements.txt`及`PROTOCOL.md`准备匹配版本。Z3 CLI和Python绑定均须为5.3.3；将其`bin`、`python`目录分别加入`PATH`、`PYTHONPATH`。
2. `--tools`指定已安装的OptiMathSAT SDK及CDCL(OCAC)目录。源码沿用执行时路径：`optimathsat-1.7.4-linux-64-bit/`与`local-nra-20261028/cvc5-ocac`。CBC和精确SCIP分别通过`CBC_BIN`、`SCIP_EXACT`指定；IPOPT/Couenne的共享库目录加入`LD_LIBRARY_PATH`。
3. 在生成目录中按`commands.json`顺序执行命令。示例中的`python`替换为对应后端的解释器；Gurobi和CPLEX须使用完整授权安装。`--core 0`等参数应替换为本机允许使用的核编号，工作进程数按本机资源调整。
4. 数值与非线性使用600秒驱动器，后者保留最终候选采集及解文件恢复规则。性能输入为97个既定实例；CGM输入直接来自归档中的1199例，无须重新下载完整上游合集；浮点包含全部1120例。

两次辅助OptiMathSAT状态查询的代码为`optimathsat_state600_20261106.py`，需要按SDK编译匹配解释器的`_optimathsat`绑定，并调整脚本开头的绑定搜索路径。原始API输出已完整保留。

累计图源码为`plot_jobshop_cumulative_20261106.py`，使用性能CSV中的440条主表调度调用。最终PDF/SVG及44个实际累计值保存在`paper/figures/05-jobshop-cumulative/`；图形导出需要Matplotlib、原字体及源码指定的布局检查工具。
