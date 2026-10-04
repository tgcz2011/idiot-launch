# backend.spec — Python 后端打包配置（Flutter 版）
# 打包为 onedir，输出到 dist/backend/
# 后端以 --server 模式启动，提供 HTTP API 给 Flutter 前端；
# 同一个 exe 通过 --countdown-app / --morning-browser 启动子功能。

# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

version_file = 'version_info_backend.txt'
if not os.path.isfile(version_file):
    version_file = None  # 还没生成时不要因为缺文件打包失败

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        # 运行时按需导入（静态分析看不到）
        'src.backend_server',
        'src.core',
        'src.morning_config',
        'src.morning_api_client',
        'src.morning_browser',
        'src.floating_button',
        'src.aria2_downloader',
        'src.telemetry',
        'countdown_app',
        'countdown_app.main',
        'countdown_app.settings',
        'countdown_app.player',
        'countdown_app.media',
        'countdown_app.cli',
        'countdown_app.win32',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'pythoncom',
        'win32com.client',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'test',
        'unittest',
        'pydoc',
        'doctest',
        'tkinter.test',
    ],
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
    exclude_binaries=True,
    name='IdiotLaunchBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,  # 出错写日志，不要把 Python 堆栈弹给老师看
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='backend',
)
