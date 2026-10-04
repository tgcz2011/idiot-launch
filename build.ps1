<#
.SYNOPSIS
    傻瓜启动器一键构建（Flutter 前端 + Python 后端 + Inno Setup 安装包）。

.DESCRIPTION
    步骤：
      1. 从 src/core.py 读取 LAUNCHER_VERSION（唯一版本源）
      2. 生成 PE 版本元数据（version_info*.txt）
      3. flutter build windows --release
      4. pyinstaller backend.spec（后端 onedir → dist\backend）
      5. ISCC IdiotLaunch.iss（安装包 → dist\IdiotLaunch_Setup_<版本>.exe）

.PARAMETER Version
    可选。传入则先调用 tools/bump_version.py 同步四处版本号再构建。
    例：.\build.ps1 -Version 3.0.0.0-beta27

.PARAMETER SkipFlutter
    跳过 Flutter 构建（只改后端时用）。

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Version 3.0.0.0-beta27
#>
param(
    [string]$Version = "",
    [switch]$SkipFlutter
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }
$VenvDir = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$CorePy = Join-Path $ProjectRoot "src\core.py"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Get-LauncherVersion {
    $m = Select-String -Path $CorePy -Pattern 'LAUNCHER_VERSION\s*=\s*"([^"]+)"'
    if (-not $m) { throw "无法从 src/core.py 读取 LAUNCHER_VERSION" }
    return $m.Matches[0].Groups[1].Value
}

# ---------- 0. 版本号 ----------
if ($Version) {
    Write-Step "同步版本号 -> $Version"
    & python (Join-Path $ProjectRoot "tools\bump_version.py") $Version
    if ($LASTEXITCODE -ne 0) { throw "版本号同步失败" }
}
$LauncherVersion = Get-LauncherVersion
Write-Host "构建版本: $LauncherVersion" -ForegroundColor Green

# ---------- 1. venv ----------
if (-not (Test-Path $Python)) {
    Write-Step "创建虚拟环境"
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
}

Write-Step "安装 Python 依赖"
& $Python -m pip install --upgrade pip | Out-Null
& $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

# ---------- 2. 版本元数据 ----------
Write-Step "生成 PE 版本元数据"
& $Python (Join-Path $ProjectRoot "tools\gen_version_info.py") $LauncherVersion "IdiotLaunch.exe" "傻瓜启动器"
& $Python (Join-Path $ProjectRoot "tools\gen_version_info.py") $LauncherVersion "IdiotLaunchBackend.exe" "傻瓜启动器后端" (Join-Path $ProjectRoot "version_info_backend.txt")
if ($LASTEXITCODE -ne 0) { throw "生成版本元数据失败" }

# ---------- 3. Flutter 前端 ----------
if (-not $SkipFlutter) {
    Write-Step "构建 Flutter 前端（release）"
    Push-Location (Join-Path $ProjectRoot "flutter_app")
    try {
        & flutter pub get
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get 失败" }
        & flutter analyze
        if ($LASTEXITCODE -ne 0) { throw "flutter analyze 未通过" }
        & flutter build windows --release
        if ($LASTEXITCODE -ne 0) { throw "flutter build 失败" }
    } finally {
        Pop-Location
    }
}

# ---------- 4. Python 后端 ----------
Write-Step "PyInstaller 打包后端"
Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean backend.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }
} finally {
    Pop-Location
}

# ---------- 5. 安装包 ----------
$ISCC = $null
foreach ($p in @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        "C:\Program Files\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $p) { $ISCC = $p; break }
}
if (-not $ISCC) {
    Write-Host ""
    Write-Host "未找到 ISCC.exe，跳过安装包（可只用于本地调试）" -ForegroundColor Yellow
    Write-Host "下载: https://jrsoftware.org/isdl.php"
    exit 0
}

Write-Step "编译安装包"
& $ISCC (Join-Path $ProjectRoot "IdiotLaunch.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败" }

# ---------- 6. 校验产物 ----------
$flutterExe = Join-Path $ProjectRoot "flutter_app\build\windows\x64\runner\Release\IdiotLaunch.exe"
$backendExe = Join-Path $ProjectRoot "dist\backend\IdiotLaunchBackend.exe"
$setupExe = Join-Path $ProjectRoot "dist\IdiotLaunch_Setup_$LauncherVersion.exe"

foreach ($f in @($flutterExe, $backendExe, $setupExe)) {
    if (-not (Test-Path $f)) { throw "构建产物缺失: $f" }
}

$hash = (Get-FileHash -Path $setupExe -Algorithm SHA256).Hash
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  构建成功  v$LauncherVersion" -ForegroundColor Green
Write-Host "  安装包: $setupExe" -ForegroundColor Green
Write-Host ("  大小:   {0:N1} MB" -f ((Get-Item $setupExe).Length / 1MB)) -ForegroundColor Green
Write-Host "  SHA256: $hash" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
