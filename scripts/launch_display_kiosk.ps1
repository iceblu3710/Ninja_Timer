#!/usr/bin/env pwsh
<#
.SYNOPSIS
Launch the TV display in Microsoft Edge kiosk mode.
#>

param(
    [int]$Port = 8000,
    [string]$HostName = "localhost"
)

$ErrorActionPreference = "Stop"
$displayUrl = "http://${HostName}:$Port/display"
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"

if (-not (Test-Path $edge)) {
    $edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}

if (-not (Test-Path $edge)) {
    throw "Microsoft Edge was not found."
}

Start-Process `
    -FilePath $edge `
    -ArgumentList @("--kiosk", $displayUrl, "--edge-kiosk-type=fullscreen") `
    -WindowStyle Hidden
