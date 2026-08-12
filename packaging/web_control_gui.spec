# -*- mode: python ; coding: utf-8 -*-
"""把 Web 服务启停控制台（web_control_gui.py）打包为 onedir 窗口程序。

与 web_server.exe 部署在同一目录；frozen 模式下直接启动同目录 web_server.exe。
控制台本身只使用标准库 Tkinter/ttk，不打包业务算法、Web 静态文件或运行数据。服务端与
Cloudflare 的进程隐藏、日志和 PID 管理由控制台源码负责，spec 只决定可执行文件形态。
"""

import os


ROOT = os.path.abspath(os.getcwd())  # build_deploy.py 从仓库根目录调用，输入路径保持稳定。

analysis = Analysis(
    [os.path.join(ROOT, "web_control_gui.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # GUI 不执行 Excel 业务，排除科学计算与测试工具，避免控制台包携带无关依赖。
    excludes=[
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
    name="峰运通服务控制台",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Tkinter 图形控制台：无控制台子系统。
    console=False,
)

# onedir 保留 Tk/Tcl 运行文件；独立内容目录避免与服务端和桥接程序的 DLL 冲突。
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="峰运通服务控制台",
    contents_directory="_internal_gui",
)
