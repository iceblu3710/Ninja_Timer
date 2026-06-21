#!/usr/bin/env pwsh
<#
.SYNOPSIS
Production launcher for the local Dynasty Ninja Timer backend.

.DESCRIPTION
Starts Uvicorn without auto-reload for gym testing or a Windows scheduled task.
Set ADMIN_PIN in the scheduled task environment or config/settings.yaml before deployment.
#>

param(
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonCmd = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonCmd)) {
    $pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
}

$env:DEBUG = "false"
$env:RELOAD = "false"

& $pythonCmd -m uvicorn app.main:app `
    --host $Host `
    --port $Port `
    --log-level info

exit $LASTEXITCODE
