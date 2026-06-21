#!/usr/bin/env pwsh
<#
.SYNOPSIS
Register a Windows scheduled task that starts the backend at user logon.
#>

param(
    [string]$TaskName = "Dynasty Ninja Timer Backend",
    [int]$Port = 8000,
    [string]$HostAddress = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\run_prod.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Missing production launcher: $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute "pwsh.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Port $Port -Host $HostAddress" `
    -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Starts the Dynasty Ninja Timer backend for local gym timing." `
    -Force
