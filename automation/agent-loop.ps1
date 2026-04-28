param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [int]$MaxRounds = 3,

    [string]$TestCommand = "pytest -q",

    [int]$AgentTimeoutSeconds = 300,

    [switch]$AutoCommit
)

$ErrorActionPreference = "Stop"

function Test-ToolAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Read-PromptTemplate {
    param([string]$Path)
    return Get-Content -LiteralPath $Path -Encoding UTF8 -Raw
}

function Invoke-ProcessWithTimeout {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = ($Arguments | ForEach-Object {
        '"' + ($_ -replace '"', '\"') + '"'
    }) -join " "
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $process.Kill($true)
        } catch {
            $process.Kill()
        }
        throw "$FilePath timed out after $TimeoutSeconds seconds."
    }

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    if ($stdout) {
        Write-Host $stdout
    }
    if ($stderr) {
        Write-Warning $stderr
    }
    if ($process.ExitCode -ne 0) {
        throw "$FilePath exited with code $($process.ExitCode)."
    }
}

function Get-CursorAgentCommand {
    $cursorAgent = Get-Command "cursor-agent" -ErrorAction SilentlyContinue
    if ($cursorAgent) {
        return [pscustomobject]@{
            File = $cursorAgent.Source
            Args = @("-p", "--force", "--output-format", "text")
        }
    }

    $agent = Get-Command "agent" -ErrorAction SilentlyContinue
    if ($agent) {
        return [pscustomobject]@{
            File = $agent.Source
            Args = @("-p", "--force", "--output-format", "text")
        }
    }

    $wsl = Get-Command "wsl" -ErrorAction SilentlyContinue
    if ($wsl) {
        & $wsl.Source -d Ubuntu -- bash -lc "test -x ~/.local/bin/agent" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $windowsRootForWsl = $root.Replace("\", "/")
            $wslWorkspace = (& $wsl.Source -d Ubuntu -- wslpath -a "$windowsRootForWsl").Trim()
            if ([string]::IsNullOrWhiteSpace($wslWorkspace)) {
                throw "Failed to convert Windows workspace path to WSL path: $root"
            }
            $shellCommandPrefix = "cd '$wslWorkspace' && ~/.local/bin/agent -p --force --trust --output-format text --workspace '$wslWorkspace'"
            return [pscustomobject]@{
                File = $wsl.Source
                Args = @("-d", "Ubuntu", "--", "bash", "-lc", $shellCommandPrefix)
                Mode = "wsl-agent"
                WslWorkspace = $wslWorkspace
            }
        }
    }

    return $null
}

function Invoke-CursorAgent {
    param([string]$Prompt)

    $command = Get-CursorAgentCommand
    if (-not $command) {
        throw "No non-interactive Cursor Agent CLI is available. Install cursor-agent or an 'agent' command before running the unattended loop."
    }

    if ($command.Mode -eq "wsl-agent") {
        $promptPath = Join-Path $root ".agent_prompt.txt"
        $runnerPath = Join-Path $root ".cursor_agent_runner.sh"
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($promptPath, $Prompt, $utf8NoBom)
        try {
            $wslPromptPath = (& $command.File -d Ubuntu -- wslpath -a ($promptPath.Replace("\", "/"))).Trim()
            $runner = @"
#!/usr/bin/env bash
set -euo pipefail
cd '$($command.WslWorkspace)'
prompt="`$(cat '$wslPromptPath')"
timeout ${AgentTimeoutSeconds}s ~/.local/bin/agent -p --force --trust --output-format text --workspace '$($command.WslWorkspace)' "`$prompt"
"@
            [System.IO.File]::WriteAllText($runnerPath, $runner, $utf8NoBom)
            $wslRunnerPath = (& $command.File -d Ubuntu -- wslpath -a ($runnerPath.Replace("\", "/"))).Trim()
            & $command.File -d Ubuntu -- bash $wslRunnerPath
            if ($LASTEXITCODE -ne 0) {
                throw "WSL Cursor Agent exited with code $LASTEXITCODE."
            }
        } finally {
            if (Test-Path -LiteralPath $promptPath) {
                Remove-Item -LiteralPath $promptPath -Force
            }
            if (Test-Path -LiteralPath $runnerPath) {
                Remove-Item -LiteralPath $runnerPath -Force
            }
        }
        return
    }

    if ($command.UsesShellPromptAppend) {
        $escapedPrompt = $Prompt.Replace("'", "'\''")
        $args = @($command.Args)
        $args[$args.Length - 1] = "$($args[$args.Length - 1]) '$escapedPrompt'"
    } else {
        $args = $command.Args + @($Prompt)
    }

    Invoke-ProcessWithTimeout `
        -FilePath $command.File `
        -Arguments $args `
        -TimeoutSeconds $AgentTimeoutSeconds
}

function Invoke-CodexAgent {
    param([string]$Prompt)

    $codex = Get-Command "codex" -ErrorAction SilentlyContinue
    if (-not $codex) {
        throw "codex command is not available, so unattended review cannot run yet."
    }

    Invoke-ProcessWithTimeout `
        -FilePath $codex.Source `
        -Arguments @("exec", $Prompt) `
        -TimeoutSeconds $AgentTimeoutSeconds
}

function Invoke-TestCommand {
    param([string]$Command)

    Write-Host "==> Running tests: $Command"
    powershell -NoProfile -Command $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed. Agent loop stopped."
    }
}

function Get-GitStatusShort {
    return git status --short
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$writerTemplate = Read-PromptTemplate "$PSScriptRoot\prompts\writer.md"
$reviewerTemplate = Read-PromptTemplate "$PSScriptRoot\prompts\reviewer.md"
$fixerTemplate = Read-PromptTemplate "$PSScriptRoot\prompts\fixer.md"

Write-Host "==> Task: $Task"
Write-Host "==> Max rounds: $MaxRounds"
Write-Host "==> Test command: $TestCommand"
Write-Host "==> Agent timeout: $AgentTimeoutSeconds seconds"

for ($round = 1; $round -le $MaxRounds; $round++) {
    Write-Host ""
    Write-Host "==> Round $round / ${MaxRounds}: implementation"

    $writerPrompt = $writerTemplate.Replace("{{TASK}}", $Task)
    Invoke-CursorAgent $writerPrompt

    Invoke-TestCommand $TestCommand

    Write-Host "==> Round $round / ${MaxRounds}: review"
    $status = Get-GitStatusShort
    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Host "No uncommitted changes. Loop finished."
        break
    }

    $reviewPrompt = $reviewerTemplate.Replace("{{TASK}}", $Task)
    Invoke-CodexAgent $reviewPrompt

    Write-Host "==> Review completed. If reviewer changed no files and tests pass, loop can stop."
    Invoke-TestCommand $TestCommand

    $fixPrompt = $fixerTemplate.Replace("{{TASK}}", $Task)
    Invoke-CursorAgent $fixPrompt

    Invoke-TestCommand $TestCommand
}

if ($AutoCommit) {
    $finalStatus = Get-GitStatusShort
    if (-not [string]::IsNullOrWhiteSpace($finalStatus)) {
        git add .
        git commit -m "Automated agent loop: $Task"
    }
}

Write-Host "==> Done."
