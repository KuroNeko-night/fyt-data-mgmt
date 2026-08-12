# -*- mode: python ; coding: utf-8 -*-
"""把桥接任务（core.tauri_bridge）打包为 onedir 程序，供 web_server.exe 子进程调用。

与 Tauri sidecar 的区别：服务端任务包含图片/发票/PDF 等业务，
必须保留 PIL、xlrd、pypdf；使用无控制台子系统避免任务运行时弹窗。

业务模块通过动作白名单动态导入，因此 hiddenimports 必须收集整个 core；这里不复制业务
算法，也不携带 Web 静态文件或运行数据。onedir 使用独立内容目录，避免与服务端依赖合并。
"""

import os

from PyInstaller.utils.hooks import collect_submodules


ROOT = os.path.abspath(os.getcwd())  # build_deploy.py 始终以仓库根目录调用 PyInstaller。

analysis = Analysis(
    [os.path.join(ROOT, "packaging", "tauri_bridge_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    # 动作模块按名称分派，静态分析无法穷举；openpyxl 写入器也需要显式保留。
    hiddenimports=collect_submodules("core") + ["openpyxl.cell._writer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 服务端桥接保留图片和 PDF 依赖，但排除开发测试、科学计算与包管理工具以控制体积。
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "numpy",
        "pandas",
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
    [],
    exclude_binaries=True,
    name="bridge_worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # web_server 以管道连接桥接任务；无控制台子系统避免任务运行时弹出 CMD 窗口。
    console=False,
)

# onedir 让多次任务启动复用磁盘依赖文件，避免每个子进程先解压单文件包。
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="bridge_worker",
    contents_directory="_internal_worker",  # 与另外两个 Windows onedir 的内容目录隔离。
)
