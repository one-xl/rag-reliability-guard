# Codex 和 Cursor 可复现协作流程

本文档用于固定本项目的“Cursor 实现、Codex 审查”协作方式，避免每次依赖临时命令和口头约定。

## 分工原则

| 任务类型 | 推荐负责方 | 原因 |
|---|---|---|
| UI、脚本、小工具、局部编辑 | Cursor | 适合在 IDE/Agent 中快速实现 |
| 后端流程、测试设计、diff 审查、风险判断 | Codex | 适合跨文件理解、终端验证和代码审查 |
| 评测实验、报告生成 | Cursor 先实现，Codex 再审查 | 兼顾产出速度和质量门禁 |

## 标准闭环

1. 明确一个小任务，不要一次塞入多个方向。
2. Cursor 作为实现者修改代码。
3. Codex 审查当前 `git diff`，只找真实问题。
4. 如果有问题，Cursor 按审查意见修复。
5. 如果 Cursor 不可用或连续失败，Codex 接手修复，并在结果中说明原因。
6. 运行测试和最小端到端验证。
7. 确认 `.env` 未进入 Git 后再提交。

## 环境自检

在仓库根目录运行：

```powershell
.\automation\check-agent-env.ps1
```

当前项目优先使用 WSL Ubuntu 中的 Cursor Agent：

```powershell
wsl -d Ubuntu -- bash -lc "~/.local/bin/agent status"
```

如果 Windows 侧只有 `cursor.cmd`，它只是 Cursor GUI 命令，不等于可无人值守写代码的 Agent CLI。

## 推荐调用方式

不要再手写复杂的 `wsl -d Ubuntu -- bash -lc "... $(cat prompt) ..."` 命令。旧方式会在 Windows 到 WSL 的命令行转义中截断中文或长提示词，导致 Cursor 误以为“需求不完整”。

现在统一使用：

```powershell
.\automation\invoke-cursor-agent.ps1 `
  -Prompt "请立即在当前仓库中修改文件：新增一个很小的测试文件。不要提交 git。" `
  -TimeoutSeconds 300 `
  -ProtectEnv
```

`-ProtectEnv` 会在调用 Cursor 前临时移走 `.env`，结束后恢复，避免外部 Agent 读取本地密钥。

## 最小连通性测试

```powershell
.\automation\invoke-cursor-agent.ps1 `
  -Prompt "Reply exactly PONG. Do not inspect or modify files." `
  -TimeoutSeconds 60 `
  -ProtectEnv
```

期望输出包含：

```text
PONG
```

如果中文在 PowerShell 中显示为乱码，但语义正确，通常是终端编码显示问题；关键是 Cursor 是否按提示执行。

## 给 Cursor 的实现提示模板

```text
请立即在当前仓库中修改文件，完成下面任务。不要只回复说明。

任务：<写清楚唯一任务>

约束：
- 不要改上传逻辑。
- 不要重构无关代码。
- 不要删除已有改动。
- 不要提交 git。

完成后列出修改文件和验证方式。
```

## Codex 审查提示模板

```text
请审查当前 git diff。先只审查，不要直接修改。
重点找逻辑 bug、边界条件、安全问题、是否破坏现有行为、是否需要补测试。
发现问题请按严重程度排序；每条说明文件位置、触发条件、影响和建议修复方式。
若无阻塞问题，请说明残余风险和是否可以 commit。
```

## 自动循环脚本

`automation/agent-loop.ps1` 已改为使用临时 prompt 文件和 WSL runner 脚本传参，避免中文和长提示词在命令行中被截断。

示例：

```powershell
.\automation\agent-loop.ps1 `
  -Task "新增一个只读的实验报告摘要脚本，不要改上传逻辑" `
  -MaxRounds 2 `
  -TestCommand ".\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp"
```

注意：当前 Codex CLI 在某些 Windows 环境中可能无法被脚本稳定调用。如果自动审查失败，可以手动把 Codex 审查提示发给当前 Codex 会话。

## 本项目的评测复现步骤

确保本地 API 正在运行后：

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py --output datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py --dataset datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py --output reports\answer_eval_report_real_papers.md
.\.venv\Scripts\python.exe scripts\evaluate_external_answers.py --dataset datasets\sample_external_answer_eval_cases.json
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

这组命令形成完整证据链：

```text
真实论文 PDF 入库
  -> 构造评测集
  -> baseline / guarded 对比实验
  -> 外部 answer/evidence 评测
  -> Markdown 实验报告
  -> 自动化测试验证
```

## 失败处理

- Cursor 返回 `[unavailable]`：记录失败，Codex 可接手当前阻塞问题。
- Cursor 回复“需求不完整”：优先检查是否绕过了 `invoke-cursor-agent.ps1`，不要使用旧的手写 WSL 命令。
- 测试失败：先让实现者修复，若连续失败再由审查者接手。
- 报告或文档出现乱码：视为阻塞问题，因为会影响论文和答辩材料。
- 不要使用 `git reset --hard` 或回滚用户改动，除非用户明确要求。
