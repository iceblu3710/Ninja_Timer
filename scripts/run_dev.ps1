#!/usr/bin/env pwsh
<#
.SYNOPSIS
Development server launcher for Dynasty Ninja Timer

.DESCRIPTION
Starts the FastAPI development server with auto-reload enabled.
Requires Python 3.12+ and uvicorn installed via pip.

.EXAMPLE
.\run_dev.ps1

.EXAMPLE
.\run_dev.ps1 -Port 9000
#>

param(
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

Write-Host "Dynasty Ninja Timer - Development Server" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python installation
$pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
Write-Host "Checking Python installation..."
$pythonVersion = & $pythonCmd --version 2>&1
Write-Host "✓ Found: $pythonVersion" -ForegroundColor Green

# Check if venv exists, create if needed
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    & $pythonCmd -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate venv
$venvActivate = "venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    Write-Host "Activating virtual environment..."
    & $venvActivate
} else {
    Write-Host "Warning: Could not find venv activation script" -ForegroundColor Yellow
}

# Install dependencies
Write-Host "Installing dependencies..."
& $pythonCmd -m pip install -q -e ".[dev]" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Start server
Write-Host "Starting development server..." -ForegroundColor Yellow
Write-Host "Server will be available at: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "  Display: http://localhost:$Port/display" -ForegroundColor Gray
Write-Host "  Admin:   http://localhost:$Port/admin" -ForegroundColor Gray
Write-Host "  Kiosk:   http://localhost:$Port/kiosk" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

$env:DEBUG = "false"
$env:RELOAD = "true"

& $pythonCmd -m uvicorn app.main:app `
    --host $Host `
    --port $Port `
    --reload `
    --log-level info

if ($LASTEXITCODE -ne 0) {
    Write-Host "Server exited with error code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
