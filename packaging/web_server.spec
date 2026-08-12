# -*- mode: python ; coding: utf-8 -*-
"""把 Web 服务端（web_server.py）打包为 onedir 程序，用于 Windows 部署整合包。

产物目录结构（与同目录 bridge_worker.exe / 服务控制台.exe 组合部署）：
    峰运通服务端.exe
    _internal/           依赖与 core 模块
    web-app/dist/        （由 build_deploy.py 在构建后复制，不依赖 datas）
运行时 ROOT 指向 exe 所在目录（web_server.py 的 frozen 分支）。

前端静态文件由 build_deploy.py 在 PyInstaller 完成后复制，运行数据则始终在部署目录的
web-data 或 FYT_WEB_DATA 指定位置生成，二者都不进入本 spec。core 与 web_backend 存在
动态动作和路由装配，因此作为 hidden imports 整体收集。
"""

import os

from PyInstaller.utils.hooks import collect_submodules


ROOT = os.path.abspath(os.getcwd())  # 构建入口保证当前目录为仓库根，避免 spec 绑定本机绝对路径。

analysis = Analysis(
    [os.path.join(ROOT, "web_server.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    # 动态业务动作、服务装配和 openpyxl 内部写入器无法仅靠 import AST 完整发现。
    hiddenimports=(
        collect_submodules("core")
        + collect_submodules("web_backend")
        + ["openpyxl.cell._writer"]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Windows Web 服务不需要 Tkinter 和开发/科学计算工具；任务图片与 PDF 依赖由桥接包承担。
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
        "test",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="web_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # EXE 保留标准控制台能力供直接前台排障；正式 GUI 通过隐藏窗口标志在后台启动它。
    console=True,
)

# onedir 可显著降低服务重启时的自解压开销，内容目录名称与其他交付 EXE 隔离。
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="web_server",
    contents_directory="_internal_web",
)
