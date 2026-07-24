# -*- mode: python ; coding: utf-8 -*-
"""把 Python 业务核心打包为 Tauri 使用的单文件 sidecar。"""

import os

from PyInstaller.utils.hooks import collect_submodules


ROOT = os.path.abspath(os.getcwd())

analysis = Analysis(
    [os.path.join(ROOT, "packaging", "tauri_bridge_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("core") + ["openpyxl.cell._writer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "qtpy",
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "numpy",
        "pandas",
        "PIL",
        "matplotlib",
        "scipy",
        "setuptools",
        "pip",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="FYTCoreBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
