# Codex 和 Cursor 可复现协作流程

本文档用于把本项目的“Cursor 写代码、Codex 审查”的协作方式固定下来，避免每次都靠临时口头约定。

## 分工原则

| 任务类型 | 推荐负责方 | 原因 |
|---|---|---|
| UI、脚本、小型工具、局部编辑 | Cursor | 适合在 IDE 中快速实现和迭代 |
| 后端流程、测试设计、diff 审查、风险判断 | Codex | 适合跨文件理解、终端验证和代码审查 |
| 评测实验、报告生成 | Cursor 先实现，Codex 再审查 | 既能快速产出，又能保留质量门禁 |

## 标准闭环

1. 明确一个小任务，不要一次塞入多个方向。
2. Cursor 作为实现者修改代码。
3. Codex 审查当前 `git diff`，只找真实问题。
4. 如果有问题，Cursor 按审查意见修复。
5. 如果 Cursor 不可用或反复失败，Codex 接手修复并说明原因。
6. 运行测试和最小端到端验证。
7. 确认 `.env` 未进入 Git 后再提交。

## 保护 `.env`

Cursor Agent 会读取项目上下文。调用外部 Agent 前，应临时移走 `.env`：

```powershell
$tmpEnv = Join-Path $env:TEMP ("bishe_env_" + [guid]::NewGuid() + ".env")
if (Test-Path .env) { Move-Item .env $tmpEnv }

# 在这里运行 Cursor Agent

if (Test-Path $tmpEnv) { Move-Item $tmpEnv .env }
```

提交前确认 `.env` 被忽略：

```powershell
git check-ignore -v .env
git status --short
```

## 环境自检

在仓库根目录运行：

```powershell
.\automation\check-agent-env.ps1
```

当前项目的可用实现入口通常是 WSL Ubuntu 中的 Cursor Agent：

```powershell
wsl -d Ubuntu -- bash -lc "cd '/mnt/c/Users/a1028/Desktop/作业们/毕设' && ~/.local/bin/agent status"
```

如果 Windows 侧只有 `cursor.cmd`，它只是 Cursor GUI 命令，不等于可无人值守写代码的 Agent CLI。

## 手动调用 Cursor Agent 的模板

将任务写入临时文件，再从 WSL 调用 Agent：

```powershell
$promptPath = ".cursor_task_prompt.txt"
Set-Content -LiteralPath $promptPath -Encoding UTF8 -Value @'
请立即在当前仓库中修改文件，完成下面任务。不要只回复说明。

任务：在这里写清楚唯一任务。

约束：
- 不要改上传逻辑。
- 不要重构无关代码。
- 不要删除已有改动。
- 不要提交 git。

完成后列出修改文件和验证方式。
'@

$root = (Get-Location).Path
$wslWorkspace = (wsl -d Ubuntu -- wslpath -a ($root.Replace("\","/"))).Trim()
$wslPrompt = (wsl -d Ubuntu -- wslpath -a ((Resolve-Path $promptPath).Path.Replace("\","/"))).Trim()
wsl -d Ubuntu -- bash -lc "cd '$wslWorkspace' && ~/.local/bin/agent -p --force --trust --output-format text --workspace '$wslWorkspace' ""`$(cat '$wslPrompt')"""
Remove-Item $promptPath
```

## Codex 审查提示模板

```text
请审查当前 git diff。先只审查，不要直接修改。
重点找逻辑 bug、边界条件、安全问题、是否破坏现有行为、是否需要补测试。
发现问题请按严重程度排序；每条说明文件位置、触发条件、影响和建议修复方式。
若无阻塞问题，请说明残余风险和是否可以 commit。
```

## 本项目的评测复现步骤

确保本地 API 正在运行后：

```powershell
.\.venv\Scripts\python.exe scripts\build_real_paper_eval_dataset.py --output datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\run_answer_eval_experiment.py --dataset datasets\real_paper_answer_eval_cases.json
.\.venv\Scripts\python.exe scripts\summarize_answer_eval_comparison.py --output reports\answer_eval_report_real_papers.md
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
```

这组命令会形成完整证据链：

```text
真实论文 PDF 入库
  -> 构造评测集
  -> baseline / guarded 对比实验
  -> Markdown 实验报告
  -> 自动化测试验证
```

## 失败处理

- Cursor 返回 `[unavailable]`：记录失败，Codex 可接手修复当前阻塞问题。
- 测试失败：先让实现者修复，若连续失败再由审查者接手。
- 报告或文档出现乱码：视为阻塞问题，因为会影响论文和答辩材料。
- 任何时候不要使用 `git reset --hard` 或回滚用户改动，除非用户明确要求。
