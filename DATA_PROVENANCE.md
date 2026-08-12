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

## 七、长超时复跑 `long600`(2026-08-12)

针对"30 s 预算太短、不足以支撑可扩展性论断"的审稿意见,以 **600 s** 超时重跑分离实验。

### 7.1 配置与规模

`configs/long600.yaml`:超时 **600 s**、**3 个种子**(取中位数)、单线程、子进程隔离、`RLIMIT_AS=4 GB`;
五个**分离族** gap/knapsack/jobshop/config/setcover(`bvcover` 为 OMT 专属、非跨范式可扩展性对比,故不含),
**81 实例 × 适用求解器 = 801 次求解**,墙钟约 **12.8 h**。

### 7.2 环境(关键)

主 harness 用 **`.venv-cplex`**(Python 3.10 + 完整 CPLEX 22.1),**不是**根目录 `.venv`。
根 `.venv` 里的 `cplex` 是 pip 的 Community 版(硬限 1000 变量),若用它跑,`cplex-ind`/`cplex-bigm`
会在 n≥160 的大实例上秒退 ERROR——恰恰是论据所在的格子(见 §五)。本次已实测确认:
`.venv` 在 1500 变量上报 `CPLEX Error 1016: Community Edition`,`.venv-cplex` 通过;
本次 `cplex-ind` 在 gap n=320(25 600 变量)上正常证明最优。

### 7.3 完整性核验

**主 run:81 个多求解器实例上,所有证明最优者目标值完全一致,0 处不符**(编码等价性成立)。
合并 Windows Gurobi 后重核,仍为 **81 实例 0 不符**。

### 7.4 Gurobi 列的来源与合并策略

WSL 的 gurobipy 仍是限额版(许可证 NODE-locked 到 Windows 主机,见 §五),在 gap n=160/320 共
**6 格**报 `Model too large for size-limited license`。补跑方式:

- 新脚本 **`scripts/gurobi_long600_windows.py`**——与旧的 `gurobi_linear_windows.py` 不同,它
  **直接 import 主 harness 的同一份代码**(`experiments.benchmarks.families.build` 还原逐字节
  相同的实例,`experiments.solvers.milp_indicator` 提供同一个原生 indicator 模型),因此与 WSL 侧
  **只差许可证,不差编码/超时/种子/实例数据**。(旧脚本硬编码 30 s、单种子、三个族,口径对不上,
  不可用于长超时复跑。)可行的前提是 Unix 专有的 `resource` 只被 `scripts/run_all.py` 使用,
  `experiments` 包本身不依赖它。
- 合并由 **`scripts/merge_gurobi_win.py`** 完成,两份原始 `results.jsonl` 均**保持不动**,只重建
  派生的 `results.csv`/`results.json`,并给每行打 `source` 标记(`wsl` / `gurobi_win`)。
- **策略:75 格取 WSL,仅 6 个许可证受限格取 Windows。** 依据:两环境都解出的 75 格**目标值逐格
  相同**、运行时中位比值 **0.92×**(最大约 2×),互换无影响;把整列固定在同一平台可避免引入
  跨平台搜索差异,而唯一需要 Windows 的理由是许可证上限而非平台。

### 7.5 数据质量备注:一处跨平台分歧

`B_jobshop_10_2` 上 WSL 限额版 Gurobi **9.04 s 证明最优**,Windows 完整版在 **600 s 内只得可行解
(目标值 61,与全体一致)未能证完**。两侧参数相同(`Threads=1`、`TimeLimit=600`、默认 MIPGap),
故属 **Linux/Windows 构建的搜索树分歧**;该实例本就处于临界(同格 CBC 290 s、SCIP 超时、
CPLEX 46.6 s,方差极大)。按 §7.4 策略该格取 WSL 值,**分歧如实记录于此,不做掩盖**。

### 7.6 状态与报错口径

801 次:**717 证明最优 · 39 仅可行 · 29 超时 · 16 报错**。16 个 ERROR 全部可归因,无框架缺陷:

| 数量 | 求解器 | 原因 | 表中标注 |
|---|---|---|---|
| 6 | `gurobi-ind` | 限额许可证(gap n≥160) | 已由 Windows 完整版补齐 |
| 3 | `gecode` | `MemoryExhausted`,4 GB 上限触发的优雅 OOM | **MO**(同 §四) |
| 5 | `highs-hull` | **SIGABRT**(`worker exit -6`),HiGHS 已知崩溃 | 求解器异常终止,**须与 T/O 区分** |
| 2 | `highs-bigm` | 同上 | 同上 |

`Gecode` 的 39 个"仅可行"里占 38 个,且 incumbent 可能远离最优(setcover n=240 跑满 600 s 报 122,
真值 21)——进表时建议一并给出 incumbent,信息量大于单标 T/O。
