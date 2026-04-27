$ErrorActionPreference = "Stop"

function Show-CommandStatus {
    param(
        [string]$Name,
        [string]$Purpose
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "[OK] $Name -> $($cmd.Source) ($Purpose)"
    } else {
        Write-Host "[MISSING] $Name ($Purpose)"
    }
}

Write-Host "==> Agent CLI environment"
Show-CommandStatus "cursor-agent" "preferred Cursor terminal agent"
Show-CommandStatus "agent" "alternate Cursor terminal agent"
Show-CommandStatus "cursor" "Cursor GUI command; not enough for unattended loop"
Show-CommandStatus "codex" "Codex CLI reviewer"

$wsl = Get-Command "wsl" -ErrorAction SilentlyContinue
if ($wsl) {
    & $wsl.Source -d Ubuntu -- bash -lc "test -x ~/.local/bin/agent" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] WSL Ubuntu agent -> ~/.local/bin/agent (usable from automation script)"
        wsl -d Ubuntu -- bash -lc '~/.local/bin/agent status'
    } else {
        Write-Host "[MISSING] WSL Ubuntu agent"
    }
}

Write-Host ""
Write-Host "==> Git"
git branch --show-current
git status --short
