# 自动化写代码-评审循环

目标：让“实现 Agent”和“审查 Agent”围绕同一个 Git 工作区循环工作，尽量减少人工介入。

当前项目已经具备自动化外壳，并已在 WSL Ubuntu 中安装 Cursor Agent CLI：

- Windows 侧检测到 `cursor` GUI 命令，但它不是无人自动写代码所需的终端 Agent。
- WSL Ubuntu 中已安装 `~/.local/bin/agent`。
- `agent status` 已显示登录账号。
- 当前环境里的 `codex.exe` 无法被脚本直接执行，启动时报 Access denied。

注意：运行 Cursor Agent 会把任务提示、相关代码上下文和工具执行结果发送给 Cursor 服务。只有在确认项目内容允许发送到外部服务后，才运行自动循环。

因此，真正的无人双 Agent 循环还需要满足：

1. Cursor Agent CLI 已可用：当前通过 WSL Ubuntu 的 `~/.local/bin/agent` 提供。
2. Codex CLI 仍需可脚本调用；当前 Windows Store 版 `codex.exe` 在脚本启动时被拒绝。
3. 或者把审查者替换成另一个可脚本调用的模型/API。

## 推荐安全流程

自动循环默认遵守：

- 每轮先让实现者改代码。
- 然后运行测试。
- 再让审查者只审查当前 diff。
- 如果审查发现问题，再让实现者修复。
- 达到最大轮数或测试失败时停止。
- 不自动提交，除非显式传入 `-AutoCommit`。

## 使用方式

确认允许 Cursor Agent 读取项目内容后运行：

```powershell
.\automation\agent-loop.ps1 -Task "为 PDF 上传接口增加文档列表接口" -MaxRounds 3 -TestCommand "pytest -q"
```

运行前可先检查环境：

```powershell
.\automation\check-agent-env.ps1
```

如果希望测试通过后自动提交：

```powershell
.\automation\agent-loop.ps1 -Task "为 PDF 上传接口增加文档列表接口" -MaxRounds 3 -TestCommand "pytest -q" -AutoCommit
```

## 当前阶段建议

在 Codex CLI 还不能被脚本调用前，最稳的是：

1. Cursor 实现。
2. Codex 审查。
3. Cursor 修复。
4. Codex 再审查。

下一小步功能建议由 Codex 实现：**文本切分模块**。理由是它更偏后端逻辑和测试，适合写清楚边界条件；Cursor 更适合后面做上传页面和评测面板。
