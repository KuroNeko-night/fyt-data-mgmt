# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包规格 —— 峰运通数据管理系统
==========================================
单目录(one-folder)模式：启动快、免每次解压、对杀软更友好，便于 Inno Setup 分发。
从 core/version.py 取应用标识；assets/ 一并打入 _internal，供 paths.assets_dir() 读取。
运行：  pyinstaller packaging/app.spec --noconfirm --clean
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.getcwd()))
sys.path.insert(0, ROOT)
from core import version as V   # noqa: E402

block_cipher = None

# 只带真正用到的静态资源(logo/图标)，排除开发用脚本
datas = [
    (os.path.join(ROOT, "assets", "icon.ico"), "assets"),
    (os.path.join(ROOT, "assets", "logo.png"), "assets"),
    (os.path.join(ROOT, "assets", "logo_128.png"), "assets"),
]

# 用不到的重型 Qt 子模块统统排除，显著减小体积
excludes = [
    "PySide2.QtNetwork", "PySide2.QtQml", "PySide2.QtQuick", "PySide2.QtQuickWidgets",
    "PySide2.QtWebEngine", "PySide2.QtWebEngineWidgets", "PySide2.QtWebEngineCore",
    "PySide2.QtWebSockets", "PySide2.QtMultimedia", "PySide2.QtMultimediaWidgets",
    "PySide2.Qt3DCore", "PySide2.QtCharts", "PySide2.QtDataVisualization",
    "PySide2.QtSql", "PySide2.QtTest", "PySide2.QtBluetooth", "PySide2.QtSensors",
    "PySide2.QtSerialPort", "PySide2.QtPositioning", "PySide2.QtLocation",
    "PySide2.QtOpenGL", "PySide2.QtXml", "PySide2.QtHelp",
    "tkinter", "unittest", "pydoc", "pytest", "numpy", "pandas", "PIL",
    "matplotlib", "scipy", "lxml", "setuptools", "pip",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    # openpyxl 惰性导入需显式带上；QtSvg 供 ui/icons.py 栅格化矢量图标(缺则图标全空白)
    hiddenimports=["openpyxl.cell._writer", "PySide2.QtSvg"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=V.APP_ID,                     # FYTDataMgmt.exe（英文名，避免中文路径问题）
    debug=False, bootloader_ignore_signals=False,
    strip=False,
    upx=False,                          # 不用 UPX：Win7 上更稳、减少杀软误报
    console=False,                      # GUI 程序，无控制台黑窗
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name=V.APP_ID,                      # 输出目录 dist/FYTDataMgmt/
)
