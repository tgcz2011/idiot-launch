<#
.SYNOPSIS
    Idiot Launch one-click build script
.DESCRIPTION
    Automates: venv creation -> dependency install -> download Countdown Desktop
    installer -> PyInstaller packaging.
    Output: dist\IdiotLaunch.exe (with Countdown Desktop installer embedded)
.PARAMETER Version
    Version number in format a.b.c.d, default 1.0.0.0
.EXAMPLE
    .\build.ps1
    .\build.ps1 -Version 1.0.0.1
#>
param(
    [string]$Version = "1.0.0.0"
)

$ErrorActionPreference = "Continue"
$ProjectRoot = $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$InstallerDir = Join-Path $ProjectRoot "installer"
$InstallerFile = Join-Path $InstallerDir "CountdownDesktop_Setup_3.2.1.1.exe"
$InstallerUrl = "https://github.com/tgcz2011/countdown-desktop/releases/download/v3.2.1.1/CountdownDesktop_Setup_3.2.1.1.exe"

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "OK: $Name" -ForegroundColor Green
}

# 1. Create venv
if (-not (Test-Path $Python)) {
    Invoke-Step "Create virtual environment" {
        python -m venv $VenvDir
    }
}

# 2. Install dependencies
Invoke-Step "Install dependencies" {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

# 3. Download Countdown Desktop installer if not present
if (-not (Test-Path $InstallerFile)) {
    Invoke-Step "Download Countdown Desktop installer" {
        if (-not (Test-Path $InstallerDir)) {
            New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
        }
        Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerFile -UseBasicParsing
    }
} else {
    Write-Host ""
    Write-Host "=== Installer already exists, skipping download ===" -ForegroundColor Yellow
}

# Verify installer
$installerSize = (Get-Item $InstallerFile).Length
if ($installerSize -lt 1MB) {
    Write-Host "FAILED: installer file abnormal (size $installerSize bytes)" -ForegroundColor Red
    exit 1
}
Write-Host "  Installer size: $([math]::Round($installerSize / 1MB, 1)) MB" -ForegroundColor Gray

# 4. PyInstaller build
Invoke-Step "PyInstaller build" {
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "IdiotLaunch.spec")
}

# 5. Verify output
$OutputExe = Join-Path $ProjectRoot "dist\IdiotLaunch.exe"
if (Test-Path $OutputExe) {
    $size = (Get-Item $OutputExe).Length
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  BUILD SUCCESS" -ForegroundColor Green
    Write-Host "  Version: $Version" -ForegroundColor Green
    Write-Host "  Output:  $OutputExe" -ForegroundColor Green
    Write-Host "  Size:    $([math]::Round($size / 1MB, 1)) MB" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "FAILED: build artifact not found: $OutputExe" -ForegroundColor Red
    exit 1
}
