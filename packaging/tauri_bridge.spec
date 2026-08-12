# -*- mode: python ; coding: utf-8 -*-
"""把 Python 业务核心打包为 Tauri 使用的单文件无窗口 sidecar。

桌面端通过标准输入输出发送带 request_id 的 JSON，不直接导入 Python。此包只包含桌面业务
需要的 core 及 Excel 依赖；Tkinter、图片/PDF 和开发工具被排除，以缩小安装程序并避免
引入第二个 GUI 运行时。最终文件由构建脚本按 Rust 目标三元组重命名。
"""

import os

from PyInstaller.utils.hooks import collect_submodules


ROOT = os.path.abspath(os.getcwd())  # npm 构建脚本在仓库根目录执行本 spec。

analysis = Analysis(
    [os.path.join(ROOT, "packaging", "tauri_bridge_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    # core 动作通过映射动态触达，PyInstaller 静态扫描无法可靠发现所有业务模块。
    hiddenimports=collect_submodules("core") + ["openpyxl.cell._writer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # PIL 等依赖不属于当前桌面白名单动作；若未来动作需要，应先更新桥接契约和测试再调整。
    excludes=[
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

# 单文件 EXE 便于 Tauri externalBin 随安装程序分发，Rust 层负责精确启动和取消进程。
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
    # Tauri 以管道连接 sidecar；使用无控制台子系统，避免桌面端启动时弹出 CMD 窗口。
    console=False,
)
