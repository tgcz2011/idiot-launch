<#
.SYNOPSIS
    Idiot Launch one-click build script
.DESCRIPTION
    Automates: venv creation -> dependency install -> PyInstaller packaging -> Inno Setup installer (compressed + store).
    Countdown Desktop 已合并到本项目，不再需要下载安装包。
    Output: dist\IdiotLaunch_Setup_<version>.exe and IdiotLaunch_Setup_<version>_store.exe
.PARAMETER Version
    Version number in format a.b.c.d or a.b.c.d-betaN, default 1.0.0.0
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

# 3. 同步版本号到 version_info.txt（用 Python 脚本生成，避免 PowerShell 编码问题）
$CorePyPath = Join-Path $ProjectRoot "src\core.py"
$LauncherVersion = (Select-String -Path $CorePyPath -Pattern 'LAUNCHER_VERSION\s*=\s*"([^"]+)"').Matches.Groups[1].Value
if ($LauncherVersion) {
    $genScript = Join-Path $ProjectRoot "tools\gen_version_info.py"
    & $Python $genScript $LauncherVersion
}

# 4. PyInstaller build
Invoke-Step "PyInstaller build" {
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "IdiotLaunch.spec")
}

# 5. Inno Setup build (if ISCC is available)
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
    # 构建两个版本：默认压缩版（自动更新用）+ 仅储存版（供测试 SmartScreen）
    Invoke-Step "Inno Setup build (compressed)" {
        & $ISCC (Join-Path $ProjectRoot "IdiotLaunch.iss")
    }
    Invoke-Step "Inno Setup build (store)" {
        & $ISCC (Join-Path $ProjectRoot "IdiotLaunch.iss") "/DCOMPRESSION=none" "/DSTOREBUILD=1"
    }
} else {
    Write-Host ""
    Write-Host "=== Inno Setup not found, skipping installer build ===" -ForegroundColor Yellow
    Write-Host "  Install from: https://jrsoftware.org/isdl.php" -ForegroundColor Gray
}

# 6. Verify output (onedir 模式：dist\IdiotLaunch\IdiotLaunch.exe)
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
