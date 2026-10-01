# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 规格文件 — Idiot Launch (v1.9.0 onedir 模式)
Countdown Desktop 已合并到本项目（countdown_app/），不再内嵌安装包。

onedir 模式说明：
- 产物为 dist/IdiotLaunch/ 目录（IdiotLaunch.exe + _internal/ 子目录 + 内嵌资源）
- 安装后 D:\IdiotLaunch\ 下有完整目录结构，像传统安装软件
- 启动更快（无需每次解压到 %TEMP%）
- 安装后的文件无 Zone.Identifier，不触发 SmartScreen
"""
import os
import sys

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("countdown_app", "countdown_app"),
        ("assets", "assets"),
    ],
    hiddenimports=[
        "pythoncom", "win32com.client", "pywintypes",
        "pystray._win32", "pystray._util", "six",
        "PIL._tkinter_finder",
        # PySide6
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtNetwork", "PySide6.QtQml", "shiboken6",
        # pywebview
        "webview", "webview.platforms.winforms", "webview.platforms.cef",
        "webview.platforms.qt", "clr", "pythonnet",
        # countdown_app 模块
        "countdown_app", "countdown_app.main", "countdown_app.player",
        "countdown_app.cli", "countdown_app.config", "countdown_app.settings",
        "countdown_app.update", "countdown_app.version", "countdown_app.win32",
        "countdown_app.media",
    ],
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
