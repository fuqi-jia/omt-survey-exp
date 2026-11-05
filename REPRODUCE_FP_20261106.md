# 公开浮点与位向量基准：600秒全量实验

本批次覆盖`o300`集合的全部1120个原始浮点实例，比较OptiMathSAT原生浮点优化、Z3浮点约束与位向量目标、Z3纯位向量转换三条路线，共3360项优化任务。原30秒批次`runs/public_fp_full_20261030/`保留。

## 输入与环境

- 输入清单：`benchmarks/public_fp/selection-full.json`，SHA-256为`bdaa85e482df4a2aa4ffd432615dbb8c7c8e5b08c1ba05456ccec32c2ba5a6c6`。
- 全部原始输入：`benchmarks/public_fp/original-fp-inputs-20261104.tar.gz`。在`benchmarks/public_fp/`解压，获得`full/fp/`目录。脚本逐项检查原始文件散列值。
- Z3 5.3.3、OptiMathSAT 1.7.4。两台机器使用相同的Z3库文件与OptiMathSAT二进制，散列值记录于交付清单。
- 两台Intel Xeon Platinum 8153机器，每台128个物理核心、每核一个工作进程，合计最多256条路线并行。每个求解、准备及核验子进程采用单线程搜索和4 GiB地址空间上限。
- 分组规则预先固定为原清单零起始偶数索引归panda1、奇数索引归panda4，各560例、1680项优化任务。各来源组均匀分布于两组。

Z3 Python包应位于`PYTHONPATH`，OptiMathSAT位于`tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat`。完整运行参数与实际Python环境保存在各组的`environment.json`和`launch.json`。

## 运行与汇总

在每台机器上执行下列Python启动片段，将`parity`分别设为0或1：

```python
import subprocess
import sys

parity = 0
indices = ",".join(map(str, range(parity, 1120, 2)))
subprocess.run([
    sys.executable, "scripts/public_fp_full_20261106.py",
    "--workers", "128", "--indices", indices,
], check=True)
```

各组完成后，在对应机器打包，将`--parity`设为其实际分组：

```bash
python scripts/collect_public_fp_20261106.py pack \
  --run runs/public_fp_full_20261106_600s --parity 0
```

将两组的交付文件分别保存在`runs/public_fp_full_20261106_600s/shards/panda1/`和`shards/panda4/`，执行：

```bash
python scripts/collect_public_fp_20261106.py merge \
  --source-a runs/public_fp_full_20261106_600s/shards/panda1 \
  --source-b runs/public_fp_full_20261106_600s/shards/panda4 \
  --output runs/public_fp_full_20261106_600s
python scripts/audit_public_fp_20261106.py
```

每组交付包括`cases.tar.gz`、`raw-logs.tar.gz`、`environment.json`、`launch.json`、`selected-indices.json`、`runner.py`与`delivery.json`。汇总脚本检查分组无交叠、索引完整、二进制及输入清单一致。

## 预算与完成标准

OptiMathSAT完整命令行进程和Z3求解子进程均限时600秒。Z3的`Optimize.check()`同时设定600000 ms内部时限；进程上限包括输入载入和输出。两条派生路线的独立编码准备进程也限时600秒，其耗时另计。

候选值在原始FP约束下接受可达性和严格改进查询，每项设600000 ms时限，双查询子进程总限时1205秒。只有可达性返回SAT、严格改进返回UNSAT，才计为完成。派生路线还要求目标上下界与返回模型的序键一致。查询未知、超时、内存超限或核验未通过均不计完成；NaN结果单列。

原生路线采用浮点数值序；派生路线排除NaN，采用正文定义的无符号序键，并区分负零与正零。核验按各路线实际声明的目标次序执行。

## 材料与核对

`cases/`保存1120例的逐路线终态与核验结果，`raw-logs.tar.gz`保存实际进程输出、返回码、原始求解记录、准备及核验记录。所有优化输入由原始文件和所存运行脚本重建。`results.csv`逐项对应来源、状态、完成分类、目标值与核验查询；`audit.json`核对全部3360项及其预算，`table-rows.tex`输出论文表12的数据行。

运行器启动阶段在panda1完成的本次600秒任务中，113条偶数索引路线直接续用，逐条终态散列值见`resumed-completed-routes.json`。未完成的启动调用不纳入正式结果；旧30秒数据不参与本批次统计。
