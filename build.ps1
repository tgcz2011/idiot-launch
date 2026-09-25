<#
.SYNOPSIS
    Idiot Launch one-click build script
.DESCRIPTION
    Automates: venv creation -> dependency install -> download Countdown Desktop
    installer -> PyInstaller packaging -> Inno Setup installer.
    Output: dist\IdiotLaunch_Setup_<version>.exe
.PARAMETER Version
    Version number in format a.b.c.d, default 1.0.0.0
#>
param(
    [string]$Version = "1.0.0.0"
)

$ErrorActionPreference = "Continue"
if ($PSScriptRoot) {
    $ProjectRoot = $PSScriptRoot
} elseif ($MyInvocation.MyCommand.Path) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    $ProjectRoot = (Get-Location).Path
}
$VenvDir = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$InstallerDir = Join-Path $ProjectRoot "installer"

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

# 3. 从 src/core.py 读取 EMBEDDED_VERSION
$CorePyPath = Join-Path $ProjectRoot "src\core.py"
$EmbeddedVersion = (Select-String -Path $CorePyPath -Pattern 'EMBEDDED_VERSION\s*=\s*"([^"]+)"').Matches.Groups[1].Value
if (-not $EmbeddedVersion) { throw "Failed to read EMBEDDED_VERSION from $CorePyPath" }
Write-Host "  Embedded Countdown Desktop version: $EmbeddedVersion" -ForegroundColor Gray
$InstallerFile = Join-Path $InstallerDir "CountdownDesktop_Setup_$EmbeddedVersion.exe"
$InstallerUrl = "https://github.com/tgcz2011/countdown-desktop/releases/download/v$EmbeddedVersion/CountdownDesktop_Setup_$EmbeddedVersion.exe"

# 4. Download Countdown Desktop installer if not present
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

# 5. PyInstaller build
Invoke-Step "PyInstaller build" {
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "IdiotLaunch.spec")
}

# 6. Inno Setup build (if ISCC is available)
$ISCC = $null
$ISCCPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($p in $ISCCPaths) {
    if (Test-Path $p) { $ISCC = $p; break }
}
if ($ISCC) {
    Invoke-Step "Inno Setup build" {
        & $ISCC (Join-Path $ProjectRoot "IdiotLaunch.iss")
    }
} else {
    Write-Host ""
    Write-Host "=== Inno Setup not found, skipping installer build ===" -ForegroundColor Yellow
    Write-Host "  Install from: https://jrsoftware.org/isdl.php" -ForegroundColor Gray
}

# 7. Verify output (onedir 模式：dist\IdiotLaunch\IdiotLaunch.exe)
$OutputExe = Join-Path $ProjectRoot "dist\IdiotLaunch\IdiotLaunch.exe"
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
