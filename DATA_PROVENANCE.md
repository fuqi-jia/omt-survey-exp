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

## 八、作业车间多种子复算 `jobshop_seeds`(2026-08-13)

回应审阅 Major 18:n=9/10 上本族种子间离散度大,3 个样本的中位数不足以支撑
**排序**结论。配置 `configs/jobshop_seeds.yaml`(job-shop n=7--10,10 seeds,
600 s,单线程,4 GB,子进程隔离),口径与 `long600` 完全一致。

### 8.1 seed 0--2 直接复用 `long600`

`build(family, size, seed)` 是确定性的,故本 run 的 seed 0/1/2 与 `runs/long600`
的对应实例**逐字节相同**;这 144 行(12 实例 × 12 求解器)直接写入本 run 的
`results.jsonl`(带 `"reused_from": "long600"` 标记),由 `--resume` 跳过重跑。
好处有二:省去 1/3 机时;且新表的多种子中位数与已发表的 3 种子数据**嵌套一致**,
复现者按 seed 0--2 重跑必得同一组数。

### 8.2 两次中断与处置(如实记录)

| 时刻 | 事件 | 处置 |
|---|---|---|
| 03:15 | **整机内存耗尽**,WSL2 重启,run 被杀 | `--resume` 续跑,已落盘 318 行全部完整、零损坏 |
| 03:15 | `B_jobshop_8_9 / cpsat` 记为 ERROR,报文 `OSError: [Errno 12] Cannot allocate memory`,**发生在 Python import 阶段、未进入求解器** | **该记录已删除**——这是宿主机事故,不是 CP-SAT 的求解失败,留下会被读成能力缺陷;已由 `--resume` 重跑 |
| 14:16 | 误判长求解为进程死亡(n=10 单格可跑满 600 s,期间日志静默),重复启动了一个同配置进程,约 10 s 后杀掉 | 未写入任何结果(`results.jsonl` 行数不变);但其与主进程同时触及了 `B_jobshop_10_6 / scip-bigm`,该格**待主 run 结束后删除重跑**(见 8.4) |

与之相对,同期的 `worker exit -6`(SIGABRT)是 HiGHS 在该模型上的**真实**原生崩溃,
与 `long600` 中的表现一致,**予以保留并计入 §四的 ERR 一档**。区分二者只能看
`error_message`,日志里同显示为 ERROR。

另:`runs/jobshop_seeds/manifest.json` 在中断后由"规模优先"重排为"**种子优先**",
使任何时刻中断都能得到各规模**种子数齐平**的可用数据集;实例内容不受影响
(名字即 family/size/seed,构造确定性)。

### 8.3 论文表格由脚本生成

`scripts/make_jobshop_table.py` 直接从 `results.jsonl` 生成 `tab:exp-jobshop` 的
LaTeX 表体,不经手工誊抄。约定:未证明最优者按 $+\infty$ 参与中位数排序(故 T/O
表示"中位数意义上未证明最优"),并以上标 `k/K` 标注 K 个种子中仅 k 个证明到最优。
仅统计**四个规模均齐**的种子,避免把 10 种子的行与 4 种子的行放在同一张表里比较。

### 8.4 收尾(已完成)

1. **已删除并重跑**两格被并发触及的单元格:`B_jobshop_10_6 / scip-bigm`(§8.2 的重复进程)
   与 `B_jobshop_10_7 / highs-bigm`(该格求解期间本机同时编译了一次论文 PDF)。
   两者均为单核负载、机器 16 线程,实际影响预计不可测量;但该两格进入论文表格,
   重跑成本仅各 ≤600 s,故未以"影响很小"代替重测。
2. **10 个种子已跑满**:480/480 格(40 实例 × 12 求解器),四个规模的 seed 0--9 全齐;
   编码等价性交叉校验 **40/40 实例目标值一致,0 处不符**。
3. 表体由 `scripts/make_jobshop_table.py --run jobshop_seeds` 生成。

### 8.5 3 seed → 10 seed 使一处论断失效

`n=10` 的 CBC 由 `516.20 s` 变为 **`T/O`**:并非变慢,而是 10 个种子中只有 5 个证明到
最优,中位数恰好跨过"半数未证明"的临界。5 个种子时它还是 `516.20`,6 个种子起即翻转
——**处在临界点上的格子,样本数一变结论就变**,这正是本次复算的意义。同类需注意的还有
`highs-bigm` 在 `n=8` 上新出现一次原生崩溃(9/10)。

其余为量值微调,方向不变:OMT 在 `n=10` 上(νZ 64.16 s、OptiMathSAT 33.66 s,均 10/10)
仍快于全部开源 MILP 与 CPLEX 指示约束;Gurobi 大-M 仍平坦(1.34 s)。

## 九、§8 补充的三组小实验(2026-08-13)

### 9.1 NRA 最优形态 C 族 —— OMT(NRA) 完整区分三种最优形态

`scripts/nra_experiment.py` 新增 C 族,考察"最优值不存在"的两种形态
(**刻意不加任何 x 的域约束**,人为下界会使两例良态化,正好毁掉被测对象):

| | 实例 | 数学真值 |
|---|---|---|
| C1 | `min x s.t. x>0 ∧ x·x>2` | 下确界 √2,**不可达** |
| C2 | `min x s.t. x·x≥1` | **下无界** |

实测(原始输出逐字保留在 `runs/nra/results.json`):

| | CDCL(OCAC) | OptiMathSAT | scipy SLSQP@5 | Gurobi NonConvex=2 |
|---|---|---|---|---|
| C1 | **`√2 + epsilon`**(√2 以代数数 `<x²−2,(5/4,3/2)>` 给出) | `1 + epsilon` | 1.4142 | OPTIMAL / 1.4142 |
| C2 | **`-oo`** | 超时 | 1.0000 | UNBOUNDED |

**结论:CDCL(OCAC) 是四者中唯一同时正确处理两种形态的**——最优可达时给精确代数数,
下确界不可达时给 `ℓ*+epsilon` 且 `ℓ*` 本身是代数数,无界时给 `-oo`。三态区分完整。

其余三者各有其限:

- **OptiMathSAT** 具备 epsilon 记号(机制存在),但在非线性实例上给出的 `ℓ*` 不正确:
  C1 上报 `1+epsilon`,而真下确界是 √2≈1.4142,`(1+ε)²≈1<2` 并不可行;其同时返回的模型为
  `x=2`,与所报目标值不符。这是增量线性化给出的弱下界。C2 上超时。
  **另需注意**:该输出**不含** `partial search` 标记,而主 harness 正是以此标记判定
  "未证明最优",故此类情形会被记为 `OPTIMAL`。不影响论文用到的任何数据(相关族均无此
  形态),但记录在案。
- **scipy SLSQP** 返回数值 1.4142 / 1.0000 并均报 `success`:C1 的数值恰等于下确界,但它
  不区分该点是否可达;C2 则完全错过无界性,停在局部。
- **Gurobi(NonConvex=2)** 无法表达严格不等式,C1 上只能求解其**闭包** `x≥0 ∧ x·x≥2`,
  故把不可达的下确界当作可达最优报为 OPTIMAL;C2 上则正确报 UNBOUNDED。

#### 9.1.1 前端触发条件(必须按此写法调用 OCAC)

在被测构建上,目标必须写成**复合项**;写成裸声明变量会走进另一条路径,返回 `check-sat`
的可行见证点且不加标记:

```
min x s.t. x>0 ∧ x·x>2     (minimize x)        -> (x 3.0)              见证点
                            (minimize (+ x 0))  -> √2 + epsilon         正确
min x s.t. x·x>=1          (minimize x)        -> (x (- 2.0))          见证点
                            (minimize (+ x 0))  -> -oo                  正确
```

`(+ x 0)` 与 `x` 语义相同,差异纯属前端。脚本因此对**两种写法都记录**
(`OBJ_FORMS`,结果存于 `by_objective_form`):只报其一,要么掩盖一个真实的调用陷阱,
要么冤枉一个正确的算法。裸变量路径的表现可证为返回可行区间中点
(`x>0∧x<1 → 1/2`,`x>10∧x<11 → 21/2`,`x>2∧x<10 → 6`)。

另记两处独立缺陷(均在 `tools/cdcl_ocac/cvc5`,release `v1.0.4-ocac-static`):
`(set-logic OMT_QF_LRA)` 与"完全无约束的 `(minimize x)`"各触发一次
**segfault(NULL pointer dereference)**。与上述能力结论无关,但复现者会遇到。

### 9.2 希尔伯特病态实验加统一目标 → `runs/illcond_obj/`

`scripts/illcond_experiment.py --objective` 给**所有**求解器统一加 `min Σᵢ xᵢ`
(PuLP 侧 `p+=0` 换为 `lpSum(x)`,Gurobi/CPLEX 用各自 API,OMT 侧加 `(minimize (+ x0 …))`)。
因 H 可逆、可行解唯一为 `x=1`,目标不可能改变返回的是哪个解,故任何格子的变化都只能
归因于优化路径本身。写入**新目录** `runs/illcond_obj/`,`runs/illcond/`(论文
`tab:exp-illcond` 的依据)**保持不动**。

结果:**48 格中 47 格逐格不变**。唯一变化:

```
cbc  n=10   correct  →  infeasible
```

已单独复现(同一 H、同一 CBC 2.10.3,仅切换目标):

```
objective = none        status=Optimal      x=[1,1,1,1,1,1,1,1,1,1]
objective = min sum x   status=Infeasible   x=[1,1,1,0,2,1,0,1,2,0]
```

即加入目标后 CBC 将这个**精确可行**的系统判为不可行(且在报 Infeasible 的同时保留了一个
残余解)。这与论文结论方向一致并构成补充:病态系统上浮点 MILP 的失败模式不仅取决于数据,
也取决于搜索路径。论文表格无需改动。

### 9.3 OMT 搜索策略调参对照 → `runs/omt_tuning/`

`scripts/omt_tuning_probe.py`:在 GAP n=160 与加权集合覆盖 n=240 上(各 3 个种子、
600 s、单线程)扫描 OMT 侧的优化搜索参数,回答"非默认搜索策略能否把这两族上 OMT 与 MILP
的差距缩小一个数量级以上"。共 6 档 × 6 实例 = **36 次求解**。

实例**不重新生成**,直接复用主 run 消费过的 `runs/long600/smt2/*.smt2`,故探针与它所论证的
表格输入逐字节相同;求解器适配器直接**子类化主 harness 的 `Z3Solver`/`OptiMathSATSolver`**
只覆写命令行,超时、单线程与"证明到最优"的判定完全沿用,口径不漂。

**两处参数名已按实际 `--help` 校正,未沿用初始设想:**

- OptiMathSAT 的搜索策略是 **`-opt.strategy=lin|bin|ada`**;`-optimization.search_strategy`
  在 1.7.4 上直接报 `unknown option`。若照后者写死,三档会退化成三份**默认配置**却看起来像
  做过对照。另注意其**默认为 `bin` 而非 `lin`**,故另设一档 `default` 用于核对默认等于哪档。
- Z3 的 `opt.priority` 只决定**多个**目标如何组合(lex/box/pareto),单目标下不起作用,
  故不计入对照;实际可调的单目标引擎开关是 **`opt.optsmt_engine=basic|symba`**。

#### 9.3.1 结果

中位数口径与 `make_jobshop_table.py` 一致:未证明最优者按 $+\infty$ 参与排序。
(初版 `summarize()` 曾对"未全部证明"直接记 T/O,会把 2/3 情形的有限中位数抹掉,已修正。)

```
=== gap n=160 ===                     中位数    证明最优   各种子
optimathsat/default(bin)              271.30     2/3     T/O / 271.3 / 216.0
optimathsat/-opt.strategy=lin         247.68     2/3     T/O / 247.7 / 188.3
optimathsat/-opt.strategy=bin         257.52     2/3     T/O / 257.5 / 227.3
optimathsat/-opt.strategy=ada         217.85     2/3     T/O / 217.8 / 172.8
z3/default(basic)                      25.92     2/3     14.7 /  25.9 / T/O
z3/opt.optsmt_engine=symba             25.33     2/3     14.5 /  25.3 / T/O

=== setcover n=240 ===   6 档 × 3 种子 = 18 次求解, 全部超时 (0/3 × 6)
```

**回答:不能。** 集合覆盖 n=240 上六档配置、三个种子共 18 次求解**全部超时**,改善为零;
GAP n=160 上各档仍在 $10^2$ 秒量级,而同族 MILP 为 $0.03$--$0.42$ s(见 `tab:exp-sep`),
差距仍是 2--3 个数量级。

**不宜宣称某一档更优。** `default(bin)` 与显式 `-opt.strategy=bin` 本是同一配置,实测相差
**5%**(271.30 对 257.52),这就是本机噪声下限;四档 OptiMathSAT 的跨度(217.9--271.3)
仅为该噪声的数倍,且下节显示同一实例跨 run 已有 2.4× 波动。z3 两档相差 2%,更在噪声内。

#### 9.3.2 数据质量备注:同一输入的跨 run 时间波动

探针与 `long600` 有 12 个共有格子(两款 OMT 默认配置 × 两族 × 3 种子),输入逐字节相同、
命令行相同。**状态(证明到最优 / 超时)12 格全部一致**,但绝对耗时存在波动:

```
z3 / gap160         seed0  14.1 → 14.7   (1.04×)
                    seed1  63.5 → 25.9   (0.41×)   同一输入相差 2.4 倍
                    seed2   T/O →  T/O
optimathsat/gap160  seed1 306.7 → 271.3  (0.88×)
                    seed2 168.6 → 216.0  (1.28×)
setcover240         6 格全部 T/O → T/O
```

`long600` 是连续 12.8 h 的长跑(机器持续高温),探针则是冷机短跑,主要怀疑对象是本机的
热降频与缓存状态。**论文所依赖的结论均为数量级判断,不受该量级波动影响**;但据此不应
在正文中比较同一族内相差不足一倍的两个 OMT 数字。
