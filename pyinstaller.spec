# -*- mode: python ; coding: utf-8 -*-
"""
Chat-Miner v1.0 PyInstaller 打包配置
one-folder 模式：生成 ChatMiner 文件夹，双击 ChatMiner.exe 启动
"""
import sys
import os
from pathlib import Path

block_cipher = None

# v1.4.1: 定位 customtkinter 资源目录
import customtkinter as _ctk
_CTK_ASSETS = os.path.join(os.path.dirname(_ctk.__file__), 'assets')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend/dist'),
        ('assets/icon.ico', 'assets/icon.ico'),
        (_CTK_ASSETS, 'customtkinter/assets'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http',
        'uvicorn.lifespan.on',
        'fastapi',
        'httpx',
        'customtkinter',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.theme',
        'customtkinter.windows.widgets.core_rendering',
        'customtkinter.windows.widgets.core_widget_classes',
        'customtkinter.windows.widgets.font',
        'customtkinter.windows.widgets.scaling',
        'customtkinter.windows.widgets.appearance_mode',
        'sqlite3',
        'asyncio',
        'logging',
        'json',
        're',
        'uuid',
        'collections',
        'datetime',
        'pathlib',
        # WeFlow 同步依赖
        'requests',
        'apscheduler',
        'apscheduler.schedulers.asyncio',
        'tzlocal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChatMiner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # v1.4.0: GUI 日志窗口替代控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ChatMiner',
)
