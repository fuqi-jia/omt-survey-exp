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

## 五、跑全矩阵的现状与限制

- **CPLEX(WSL 可用完整版)**:用 **`.venv-cplex`**(python 3.10 + CPLEX Studio 22.1 完整 API)即可无限制求解;`.venv-cplex/bin/python scripts/run_all.py …` 全程走完整 CPLEX。pip 的 `cplex`(community)硬限 1000 变量、**许可证无法解锁**,故默认 `.venv`(py3.12)仍是限额版——跑实验统一用 `.venv-cplex` 即可避免 CPLEX 回退。
- **Gurobi(WSL 用不了完整版)**:完整许可证是 **NODE-locked 到 Windows 主机**(`gurobi.lic` TYPE=NODE),WSL2 主机 id 不同 → **WSL 的 gurobipy 仍是限额版,无法用完整许可证**。完整 Gurobi 只能在 Windows 上跑:`scripts/run_gurobi_windows.ps1` → `scripts/gurobi_linear_windows.py` → `runs/gurobi_win/`。
- 因此**"单机一次跑完含完整 Gurobi 的全矩阵"目前做不到**。两条路:
  1. **沿用现状**(论文即此法):WSL `.venv-cplex` 跑除 Gurobi 外的全部(含完整 CPLEX)+ Windows 单跑 Gurobi,再合并——已交叉校验目标值一致(见第三节)。
  2. 换一张**非 node-locked 的 Gurobi 许可证**(学术 named-user / WLS 浮动证),才能在 WSL 内跑完整 Gurobi、真正单机一次跑完。

## 六、精确性实验补充:exact-SCIP(精确有理 MILP)

为严格回答"精确 MILP 是否也精确"而非以限定词回避,从源码自建了 **SCIP 11.0.0 的 exact 求解模式**(`EXACTSOLVE=ON` + GMP/MPFR + 精确 SoPlex 9.0.0;构建步骤见 `tools/scip-exact/BUILD.md`,二进制 gitignore)。`scripts/exact_experiment.py` 新增 `scip-exact` 求解器(`SOLVERS` 中),数据回填 `runs/exact/`。

结果(每格 10 实例):`scip-exact` 在 **2^40 / 2^54 / 2^60 均 10/10 精确**(浮点 MILP 在 2^54+ 已失效),证实**大系数失效源于浮点算术、而非 MILP 范式**;但 SCIP 将绝对值超过其有限值上限(`numerics/infinity` ≈ 1e20,不可调高过上限)的系数视为无穷而**拒绝读入**,故 **2^200 安全拒解**;唯有 OMT(任意精度有理,无此上限)在所有量级精确。论文 `tab:exp-exact`、`tab:exp-tools` 与 §8 结果段/观察3 已据此改写为严格四档结论,删去原"仅 OMT 精确"的过强表述。
