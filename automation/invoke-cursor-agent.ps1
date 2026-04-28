param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [int]$TimeoutSeconds = 300,

    [switch]$ProtectEnv
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$wsl = Get-Command "wsl" -ErrorAction SilentlyContinue
if (-not $wsl) {
    throw "wsl command is not available."
}

& $wsl.Source -d Ubuntu -- bash -lc "test -x ~/.local/bin/agent" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Cursor Agent is not available at WSL Ubuntu ~/.local/bin/agent."
}

$tempEnv = $null
if ($ProtectEnv -and (Test-Path -LiteralPath ".env")) {
    $tempEnv = Join-Path $env:TEMP ("rag_guard_env_" + [guid]::NewGuid().ToString() + ".env")
    Move-Item -LiteralPath ".env" -Destination $tempEnv
}

$promptPath = Join-Path $root ".agent_prompt.txt"
$runnerPath = Join-Path $root ".cursor_agent_runner.sh"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

try {
    [System.IO.File]::WriteAllText($promptPath, $Prompt, $utf8NoBom)

    $wslWorkspace = (& $wsl.Source -d Ubuntu -- wslpath -a ($root.Replace("\", "/"))).Trim()
    if ([string]::IsNullOrWhiteSpace($wslWorkspace)) {
        throw "Failed to convert workspace path to WSL path: $root"
    }

    $wslPromptPath = (& $wsl.Source -d Ubuntu -- wslpath -a ($promptPath.Replace("\", "/"))).Trim()
    $runner = @"
#!/usr/bin/env bash
set -euo pipefail
cd '$wslWorkspace'
prompt="`$(cat '$wslPromptPath')"
timeout ${TimeoutSeconds}s ~/.local/bin/agent -p --force --trust --output-format text --workspace '$wslWorkspace' "`$prompt"
"@
    [System.IO.File]::WriteAllText($runnerPath, $runner, $utf8NoBom)
    $wslRunnerPath = (& $wsl.Source -d Ubuntu -- wslpath -a ($runnerPath.Replace("\", "/"))).Trim()

    & $wsl.Source -d Ubuntu -- bash $wslRunnerPath
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
    if ($tempEnv -and (Test-Path -LiteralPath $tempEnv)) {
        Move-Item -LiteralPath $tempEnv -Destination ".env"
    }
}
