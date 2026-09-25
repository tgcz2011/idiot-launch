# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 规格文件 — Idiot Launch (v1.7.0.0 onedir 模式)
打包时将 Countdown Desktop 安装包作为数据文件内嵌。
构建前请确保 installer/CountdownDesktop_Setup_3.2.1.1.exe 存在（build.ps1 会自动下载）。

onedir 模式说明：
- 产物为 dist/IdiotLaunch/ 目录（IdiotLaunch.exe + _internal/ 子目录 + 内嵌资源）
- 安装后 D:\IdiotLaunch\ 下有完整目录结构，像传统安装软件
- 启动更快（无需每次解压到 %TEMP%）
- 安装后的文件无 Zone.Identifier，不触发 SmartScreen
"""
import os
import sys

block_cipher = None

# 内嵌安装包路径
INSTALLER_PATH = os.path.join("installer", "CountdownDesktop_Setup_3.2.1.1.exe")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        (INSTALLER_PATH, "installer"),
        ("assets", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries/datas 由 COLLECT 收集，不打进 exe
    name="IdiotLaunch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 强制不使用 UPX 压缩壳，降低 SmartScreen/杀软误报概率
    console=False,  # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",  # 应用图标（手指点击图案）
    version='version_info.txt',  # 注入完整版本元数据
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IdiotLaunch",
)
