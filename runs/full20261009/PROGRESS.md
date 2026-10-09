# 全集实验工作记录

截至 2026-10-09 11:27 UTC（仍在运行，不是最终结果）。

- 主稿：已从 GitHub 快进到 `GOMT/main@cd556a6`；原有 CLAUDE.md 与 Word 模板的本地改动保留。摘要与关键词冻结，正文尚未覆盖作者的新修订。
- 控制面：现有 ExperimentOS，`jiafq@192.168.20.110:/pub/data/jiafq/experimentos`。实验仓库在 `/pub/data/jiafq/omt-survey-exp`，基线 `f440ce0`。
- MaxSMT：完整 2,264 个标准输入已提交，ExperimentOS ID `39a26fbbb146`，名称 `jos-full-maxsmt-20261009-r1`。四种配置，共 9,056 次求解。平台预检已通过，首个实例四种配置都通过最优性复核；最新观测 481 个作业完成、171 个运行、1,612 个等待。
- MaxSMT 输入审计：全量解析识别 19 个原始损坏输入；其中 8 个 query-901 变体语法错误，11 个加权文件被原包截断为 262,144 字节。本地原 RAR 与控制面一致。全部保留并实际调用求解器记录响应，不能作为有效最优结果。
- FP：完整 39,655 个任务已提交，ExperimentOS ID `36446869763f`，名称 `jos-full-fp-20261009-r1`；三种配置共 118,965 次求解。全部 17,314 个源文件均有派生任务，发布包的 1,120 项全部覆盖；全量解析 39,655/39,655 通过。原生成器产生 39,638 项，补齐未识别目标 16 项，加上发布包中一个内容不同的文件；补充项含空公式源的两个退化任务，详见 README。
- BV：原始公开包完整下载且哈希已核对，包含 254 个 BV 和对应 254 个 LIA 文件，正在传入控制节点。不要将尚未完成的 `.xz.partial` 传输试验产物作为输入；正式源包是完整 `tacas16.tar.gz`。

## 后续必须完成

1. 监控已提交的 FP 全集及平台预检，收取完整清单、覆盖记录和运行日志；不要重复生成清单或重复提交。
2. 核对控制节点 BV 原始压缩包 SHA256，运行 `prepare.py bv`，全量解析 BV 与 LIA，生成规格并全部提交。
3. 监控各组全部任务直到终态。逐项核对计划清单、求解结果和原始日志；重试基础设施故障，调查适配器错误与最优性反例，不能靠排除失败样本完成任务。
4. 收集控制面及执行节点的完整日志和环境信息，保存本地与实验仓库。汇总时区分完整发布包、语法有效输入、求解器声称最优和独立验证最优；保留超时和 OOM 的分母。
5. 所有实验完成后更新 LaTeX 实验章节、逐条回复与复现指针，保持摘要冻结，编译并验证 PDF。提交和推送相应仓库。

## 常用命令

本地查询控制面（不读取凭据）：

```bash
python3 scripts/full_campaign/remote.py scripts/full_campaign/control_status.py
```

控制节点工作目录 `/pub/data/jiafq/omt-survey-exp`：

```bash
python3 scripts/full_campaign/finalize_fp.py
python3 scripts/full_campaign/validate_inputs.py fp
python3 scripts/full_campaign/prepare.py bv
python3 scripts/full_campaign/validate_inputs.py bv
python3 scripts/full_campaign/validate_inputs.py bv_lia
python3 scripts/full_campaign/spec.py fp
# spec.py 支持 fp / bv / bv_lia / maxsmt；先 dry-run，再 submit --yes。
```

Windows SSH 转发已能连接控制节点。大文件传输必须用 `scp -O`，默认 SFTP 模式实测非常慢。`remote.py` 只包装 Python 脚本的安全压缩传输。

BV 中转：完整 1.55 GB 原包已上传实验仓库的草稿 release `full-benchmarks-20261009`（尚未发布），asset ID `624731327`；从控制节点经临时签名链接下载后必须核对原始 SHA256。GitHub 凭据不传入集群。慢速直接 SCP 仍是未完成副本，不能作为输入。
