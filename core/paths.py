# -*- coding: utf-8 -*-
"""
应用路径与业务输出目录的单一事实来源
======================================
集中解析配置、主数据库、本机缓存、任务历史、崩溃日志、美术资源和各业务输出目录，
避免功能模块根据当前工作目录或界面入口自行拼接路径。桌面默认数据根为当前用户
“文档/峰运通数据管理系统”，Web 任务则通过环境变量把配置和输出指向用户隔离目录。

默认业务输出结构为：

    文档/峰运通数据管理系统/输出/<功能中文名>/<时间戳>/文件...

同时支持源文件旁 ``output`` 和自定义根目录。输出目录使用原子创建方式竞争唯一名称，
同一分钟或并发任务不会写入同一目录。应用数据目录函数会按需创建目录；只返回文件
路径的函数不创建文件本身，实际写入错误由业务调用点明确暴露。
"""
import os
import sys
import datetime

from . import version

# Web 业务目录和打包文档均依赖此映射；新增输出类型必须在这里注册中文客户名称。
FEATURE_DIRS = {
    "attendance": "考勤填报",
    "attendance_archive": "考勤月度归档",
    "reconcile_statement": "对账单制作",
    "reconcile": "工时对账",
    "arrival": "到料明细",
    "pivot": "透视表",
    "pdf_tools": "PDF工具",
    "excel_tools": "Excel工具",
    "purchase": "采购数对账",
    "delivery": "送货计划",
    "supplier_batch": "供应商批次表",
    "purchase_plan": "采购计划导入",
    "master_data": "主数据库",
    "workshop_issue": "车间每日问题",
    "daily_report": "日清报告",
    "daily_safety_check": "安全检查日报",
    "invoice": "增值税发票统计",
    "invoice_match": "票货匹配",
    "compare": "表格比对",
}


def app_dir():
    """返回程序资源基准目录。

    PyInstaller 冻结后使用可执行文件所在目录；源码运行时从 ``core`` 文件的上一级
    得到项目根，不依赖调用进程的当前工作目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def documents_dir():
    """解析当前 Windows 用户的“文档”目录，失败时退回用户主目录。

    优先调用 Shell API，而不是假定目录名为 Documents，因为中文系统、OneDrive
    重定向和企业策略都可能改变真实位置。非 Windows 或 API 不可用时的回退也让
    核心模块可在 Linux 服务端测试和运行。
    """
    try:
        import ctypes.wintypes
        CSIDL_PERSONAL = 5  # Windows Shell 的“我的文档”目录标识。
        SHGFP_TYPE_CURRENT = 0
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None,
                                               SHGFP_TYPE_CURRENT, buf)
        if buf.value and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        # 路径探测属于兼容能力，失败后仍有跨平台的用户主目录可用。
        pass
    return os.path.expanduser("~")


def app_data_dir():
    """返回并确保桌面应用数据根目录存在。"""
    d = os.path.join(documents_dir(), version.APP_NAME)
    _ensure(d)
    return d


def default_output_root():
    """返回并确保统一业务输出根目录存在。"""
    d = os.path.join(app_data_dir(), "输出")
    _ensure(d)
    return d


def library_dir():
    """返回并确保本机业务资料数据库目录存在。"""
    d = os.path.join(app_data_dir(), "数据库")
    _ensure(d)
    return d


def library_index_path():
    """返回资料数据库索引 JSON 路径，不创建索引文件。"""
    return os.path.join(library_dir(), "索引.json")


def assets_dir():
    """返回品牌图片和图标等静态资源目录。

    PyInstaller 单文件/单目录包会把资源释放到 ``sys._MEIPASS``；只有该位置实际存在
    assets 时才使用它，否则回退到程序目录，兼容源码和未内嵌资源的开发构建。
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base and os.path.isdir(os.path.join(base, "assets")):
            return os.path.join(base, "assets")
    return os.path.join(app_dir(), "assets")


def config_path():
    """返回全局配置路径；Web/测试可通过 ``FYT_CONFIG_PATH`` 完整覆盖。"""
    override = os.environ.get("FYT_CONFIG_PATH", "").strip()
    if override:
        # 环境变量可能是相对路径，立即转绝对路径避免子进程工作目录变化。
        return os.path.abspath(override)
    return os.path.join(app_data_dir(), "配置.json")


def crash_log_path():
    """返回统一崩溃日志文件路径。"""
    return os.path.join(app_data_dir(), "错误日志.txt")


def task_history_path():
    """返回本机任务历史 SQLite 路径，并允许环境变量隔离测试或 Web 用户。"""
    override = os.environ.get("FYT_TASK_HISTORY_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(app_data_dir(), "任务历史.db")


def incremental_cache_path():
    """返回增量缓存索引路径，并允许环境变量覆盖。"""
    override = os.environ.get("FYT_INCREMENTAL_CACHE_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(app_data_dir(), "增量缓存.json")


# 当前文件超过 512 KB 后轮转为一个 .old；最多保留约两倍上限，避免长期运行无限增长。
_CRASH_LOG_MAX = 512 * 1024


def append_crash_log(text):
    """为格式化错误正文补充时间戳并追加到有界崩溃日志。

    写入前若当前文件达到上限，将其原子替换为唯一一份 ``.old``；旧 ``.old`` 先删除。
    轮转失败不阻断本次追加，整个日志路径也绝不向业务层抛异常，避免记录原始故障时
    再产生第二个故障并掩盖真正错误。
    """
    try:
        p = crash_log_path()
        # 轮转只保留一个历史文件，空间有界且用户仍能查看上一段日志。
        try:
            if os.path.isfile(p) and os.path.getsize(p) >= _CRASH_LOG_MAX:
                old = p + ".old"
                if os.path.isfile(old):
                    os.remove(old)
                os.replace(p, old)
        except OSError:
            pass  # 权限或占用导致轮转失败时继续追加，日志可能暂时超过上限。
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n%s\n" % (stamp, text))
    except Exception:
        pass  # 日志是诊断辅助，不能改变业务成功或失败状态。


def timestamp():
    """返回分钟级本地时间戳 ``YYYYMMDD_HHMM``，供同批输出统一命名。"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def resolve_output_dir(feature, mode="unified", src_path=None,
                       custom_root=None, ts=None):
    """按运行环境和用户设置解析并原子创建一次业务输出目录。

    ``feature`` 通过 ``FEATURE_DIRS`` 转为中文子目录；``mode`` 支持统一目录、源文件旁
    和自定义根。Web 设置 ``FYT_WEB_OUTPUT_ROOT`` 后拥有最高优先级，服务端预先把它
    指向当前用户和任务的隔离根，不能再受桌面输出模式影响。``ts`` 可由同一批任务
    共用，但目录仍会自动追加序号避免冲突。返回已创建的绝对或规范化目录路径。
    """
    ts = ts or timestamp()
    feat_cn = FEATURE_DIRS.get(feature, feature)
    web_root = os.environ.get("FYT_WEB_OUTPUT_ROOT", "").strip()
    if web_root:
        # Web 隔离根由服务端校验所有权；核心层只在其下增加功能分类。
        base = os.path.join(os.path.abspath(web_root), feat_cn)
    elif mode == "beside" and src_path:
        base = os.path.join(os.path.dirname(os.path.abspath(src_path)), "output")
    elif mode == "custom" and custom_root:
        base = os.path.join(custom_root, feat_cn)
    else:  # unified
        base = os.path.join(default_output_root(), feat_cn)
    # 分钟级时间戳可能碰撞，原子认领目录会追加 _2/_3；调用方应每批只解析一次，
    # 再把同一批的多个输出写入返回目录。
    return _claim_unique_dir(os.path.join(base, ts))


def _unique_dir(path):
    """只计算尚不存在的候选目录名，不执行创建。

    这是保留给旧调用方的非原子辅助函数；并发业务应使用 ``_claim_unique_dir``，避免
    两个进程在检查与创建之间同时选择同一路径。
    """
    if not os.path.exists(path):
        return path
    i = 2
    while True:
        cand = "%s_%d" % (path, i)
        if not os.path.exists(cand):
            return cand
        i += 1


def _claim_unique_dir(path):
    """通过 ``os.mkdir`` 的排他创建语义认领唯一目录并返回实际路径。

    父目录允许并发安全地存在；候选目录已存在时捕获 ``FileExistsError`` 并递增后缀。
    其他权限、磁盘或路径错误不吞掉，由业务入口向用户报告。
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    i = 1
    while True:
        candidate = path if i == 1 else "%s_%d" % (path, i)
        try:
            os.mkdir(candidate)
            return candidate
        except FileExistsError:
            i += 1


def _ensure(d):
    """递归创建目录并返回原参数；权限或磁盘错误保持向上抛出。"""
    os.makedirs(d, exist_ok=True)
    return d
