# 数据来源与完整性记录

> 记录分离实验表 (`sections/exp-evaluation.tex` 的 `tab:exp-sep`) 各列数据来源、为何商业
> 求解器单独跑、以及一次完整的目标值交叉核验结论 (2026-06-28)。

## 一、`tab:exp-sep` 各列数据来源(多 run 合并)

| 列 | 来源 run | 说明 |
|---|---|---|
| νZ (z3)、OptiMathSAT | `runs/sep` + `runs/sep_large` | OMT;中小规模在 sep,大规模在 sep_large |
| CBC / HiGHS / SCIP | `runs/sep` + `runs/sep_large` | 开源 MILP |
| Gecode / CP-SAT | `runs/sep` + `runs/sep_large` | CP |
| **Gurobi** | **`runs/gurobi_win/results.json`** | **Windows 全许可证**,`scripts/gurobi_linear_windows.py` 单独跑 |
| **CPLEX** | **`runs/cplex_lin/results.json`** | **Linux 全许可证**,`scripts/cplex_linear.py` 单独跑 |
| 集合覆盖族 Gurobi/CPLEX | `runs/setcover` | 模型较小,未超免费上限,主 harness 即可跑出 |

gurobi_win/cplex_lin 的 JSON schema 与主 harness 不同:`{family, n, seed, nvars, solve_s, proved_optimal, objective, exceeds_restricted_cap}`(无 `solver`/`status`/`size` 字段)。

## 二、为何 Gurobi/CPLEX 要单独跑

主 harness `scripts/run_all.py` 在 WSL `.venv` 中调用的是 **pip 默认的限额免费版**:

- CPLEX community:`**** Promotional version. Problem size limits (1000 vars, 1000 consts) exceeded` → 大模型秒退 `ERROR`(mem=0、~0.004s)。
- Gurobi size-limited:`Model too large for size-limited license` → 大模型秒退 `ERROR`。

因此 `runs/sep`、`runs/sep_large` 里 `gurobi-ind`/`cplex-ind` 在大实例上是 ERROR,**不进表**。表中 Gurobi/CPLEX 取自上面的**全许可证专跑**;`gurobi_win` 记录里 `exceeds_restricted_cap=True`(gap160/320/640、knapsack2560)正印证这些模型超过免费上限、确由全许可证求解。

> 结论:作者**持有完整 Gurobi/CPLEX 许可证**;免费版仅在 WSL `.venv` 这一环境里作为默认回退出现,表用的不是它。

## 三、完整性核验(2026-06-28)

对 `runs/*/results.json` 全量做"证明最优者目标值是否一致"的逐实例交叉核对(gap/config/knapsack/setcover × 各规模,seed 0):

- **16 个分离实例上,喂表的所有源(gurobi_win、cplex_lin、sep_large、sep、setcover)目标值完全一致** → 全许可证跑解的是**同一批实例**,非旧数据/异构数据。
- 唯一分歧:`runs/sep_lin`(辅助跑,**未用于表**)的 `cplex-ind` 在 `knapsack2560` 上报 `20381`,真值与其余全部为 `20382`(差一,疑 CPLEX 容差/缩放)。**不影响论文**,仅作数据质量备注。

## 四、`tab:exp-sep` 四态含义

`数字`=证明最优 · `可行`=得可行解未证明最优(SAT)· `T/O`=超时(30 s)· `MO`=超 4 GB 内存上限。

3 个 `MO` 格(νZ gap640、Gecode gap320/640)经 `error_message` 确认为**优雅 OOM 而非崩溃**:
z3 `(error "out of memory")`、Gecode `Gecode::MemoryExhausted (Heap memory exhausted)`;由 `run_all.py` 的 `RLIMIT_AS=4 GB` 触发。属资源限额,非求解器缺陷。

## 五、TODO:单机跑全矩阵(避免回退免费版)

要在一个 WSL 环境一次跑完全矩阵(含全许可证 Gurobi/CPLEX):

- **Gurobi**:设 `GRB_LICENSE_FILE` 指向完整 `gurobi.lic`,同一 `gurobipy` 即用全许可证(无需换包)。
- **CPLEX**:pip `cplex`(community)硬限 1000 变量、许可证无法解锁;须用 **CPLEX Studio 完整安装**的 Python API(参见 `.venv-cplex`,python 3.10)。让 `run_all.py` 在该环境调用完整 CPLEX。根目录已有安装包 `cplex_studio2210.linux_x86_64.bin`。
- 接上后,`gurobi-ind`/`cplex-ind` 即可在大实例上正常求解,`gurobi_win`/`cplex_lin` 专跑可并入主矩阵。
