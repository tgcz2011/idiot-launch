# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 规格文件 — Idiot Launch
打包时将 Countdown Desktop 安装包作为数据文件内嵌。
构建前请确保 installer/CountdownDesktop_Setup_3.2.0.0.exe 存在（build.ps1 会自动下载）。
"""
import os
import sys

block_cipher = None

# 内嵌安装包路径
INSTALLER_PATH = os.path.join("installer", "CountdownDesktop_Setup_3.2.0.0.exe")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        (INSTALLER_PATH, "installer"),
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="IdiotLaunch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如有图标可设置 assets/icon.ico
)
