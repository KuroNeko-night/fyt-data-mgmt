# -*- coding: utf-8 -*-
"""
统一路径系统 —— 解决"各功能输出目录各不相同"的混乱
=====================================================
原状况：考勤/对账写到「源文件目录/output」，到料/透视写到「程序目录/output」，
用户找不到结果在哪。现统一为：

    <文档>/峰运通数据管理系统/输出/<功能中文名>/<时间戳>/文件...

· 位置固定、可预测、按功能归档；
· 也支持"源文件旁 output/"与"自定义目录"两种模式（见 settings）。

兼容 Windows 7 + Python 3.8。
"""
import os
import sys
import datetime

from . import version

# 各功能的中文归档名（输出根目录下的子文件夹）
FEATURE_DIRS = {
    "attendance": "考勤填报",
    "reconcile": "工时对账",
    "arrival": "到料明细",
    "pivot": "透视表",
    "pdf_tools": "PDF工具",
    "excel_tools": "Excel工具",
    "purchase": "采购数对账",
    "delivery": "送货计划",
}


def app_dir():
    """程序所在目录：打包后为 exe 所在目录，源码运行为本文件上一级(项目根)。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def documents_dir():
    """当前用户"文档"目录；取不到则退回用户主目录。兼容 Win7。"""
    try:
        import ctypes.wintypes
        CSIDL_PERSONAL = 5          # My Documents
        SHGFP_TYPE_CURRENT = 0
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None,
                                               SHGFP_TYPE_CURRENT, buf)
        if buf.value and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        pass
    return os.path.expanduser("~")


def app_data_dir():
    """应用数据目录：<文档>/峰运通数据管理系统。存放配置、输出根、崩溃日志。"""
    d = os.path.join(documents_dir(), version.APP_NAME)
    _ensure(d)
    return d


def default_output_root():
    """默认输出根目录：<文档>/峰运通数据管理系统/输出。"""
    d = os.path.join(app_data_dir(), "输出")
    _ensure(d)
    return d


def library_dir():
    """数据库根目录：<文档>/峰运通数据管理系统/数据库。程序自带的表存储。"""
    d = os.path.join(app_data_dir(), "数据库")
    _ensure(d)
    return d


def library_index_path():
    """数据库索引文件（记录每张表的类别/更新日期/元信息）。"""
    return os.path.join(library_dir(), "索引.json")


def assets_dir():
    """静态资源目录（logo/图标）。

    打包后随程序一并携带：PyInstaller 会把 assets/ 释放到 _MEIPASS
    （单文件=临时目录；单目录=_internal）。源码运行时取项目根下的 assets/。
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base and os.path.isdir(os.path.join(base, "assets")):
            return os.path.join(base, "assets")
    return os.path.join(app_dir(), "assets")


def config_path():
    """全局配置文件路径。"""
    return os.path.join(app_data_dir(), "配置.json")


def crash_log_path():
    """崩溃日志路径（统一到应用数据目录，两程序原来各写各的）。"""
    return os.path.join(app_data_dir(), "错误日志.txt")


def timestamp():
    """时间戳 YYYYMMDD_HHMM，用于输出子文件夹与文件名。"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def resolve_output_dir(feature, mode="unified", src_path=None,
                       custom_root=None, ts=None):
    """按设置解析某次运行的输出目录并创建它。

    feature    : "attendance"/"reconcile"/"arrival"/"pivot"
    mode       : "unified"=文档下统一文件夹(默认) / "beside"=源文件旁 output/ / "custom"=自定义根
    src_path   : beside 模式下用来定位源文件目录
    custom_root: custom 模式下的根目录
    ts         : 时间戳；不传自动生成。同一批次可共用一个。
    返回创建好的目录绝对路径。
    """
    ts = ts or timestamp()
    feat_cn = FEATURE_DIRS.get(feature, feature)
    if mode == "beside" and src_path:
        base = os.path.join(os.path.dirname(os.path.abspath(src_path)), "output")
    elif mode == "custom" and custom_root:
        base = os.path.join(custom_root, feat_cn)
    else:  # unified
        base = os.path.join(default_output_root(), feat_cn)
    out = os.path.join(base, ts)
    _ensure(out)
    return out


def _ensure(d):
    """确保目录存在，失败静默（调用方会在真正写文件时再暴露错误）。"""
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
    except Exception:
        pass
    return d
