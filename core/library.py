# -*- coding: utf-8 -*-
"""
桌面端本机文件库核心：自动分类、归档与索引
========================================
用户把各处来的 Excel 拖进来，程序据"文件名 + 表头"双阶段评分自动判定用途，
复制归档到 <文档>/峰运通数据管理系统/数据库/<类别>/，记录最后更新日期等元信息；
未能识别的表统一进"未识别"文件夹。各功能页可据类别自动取到所需的表。

类别（10 类 + 未识别）：
  att_source   填报·系统数据表（打卡来源）
  att_target   填报·待填考勤表
  rec_source   对账·数据来源（工时明细）
  rec_zong     对账·待对总表
  rec_labor    对账·劳务对账单
  pivot_src    透视·采购数据表
  arrival_plan 到料·送货计划表
  purchase_stmt 采购·采购对账单（我方/供方通用）
  deliv_bom    送货·物料清单（KD/SUB 物料清单）
  deliv_supp   送货·供应商明细（含供应商代码/名称）
  unknown      未识别

分类结果允许一个文件带多个业务标签，但物理文件只归档到主类别目录；索引读改写使用
文件锁和临时文件原子替换，防止多个任务并发导入时丢失条目。本模块是桌面端本机文件库，
Web 数据库的按用户权限与存储隔离由服务端实现，不能直接复用这里的绝对路径索引。
"""
import os
import json
import shutil
import datetime

from . import library_scan, library_storage, paths
from .library_classification import SCORERS, score_sheet
from .storage_lock import file_lock

# 类别顺序同时决定桌面端展示顺序；新增业务分类必须同步标题、目录和评分规则。
CATEGORIES = ["att_source", "att_target", "rec_source", "rec_zong",
              "rec_labor", "pivot_src", "arrival_plan",
              "purchase_stmt", "deliv_bom", "deliv_supp"]
UNKNOWN = "unknown"

# ``CATEGORIES`` 仍是对外单一事实源；启动时校验规则注册顺序，防止新增类别只改一处。
if [category for category, _scorer in SCORERS] != CATEGORIES:
    raise RuntimeError("文件库类别与分类评分规则未同步")

CATEGORY_TITLES = {
    "att_source": "填报 · 系统数据表",
    "att_target": "填报 · 待填考勤表",
    "rec_source": "对账 · 数据来源",
    "rec_zong": "对账 · 待对总表",
    "rec_labor": "对账 · 劳务对账单",
    "pivot_src": "透视 · 采购数据表",
    "arrival_plan": "到料 · 送货计划表",
    "purchase_stmt": "采购 · 采购对账单",
    "deliv_bom": "送货 · 物料清单",
    "deliv_supp": "送货 · 供应商明细",
    "unknown": "未识别",
}
# 归档目录使用中文业务名称，方便管理员脱离程序直接检查本机文件库。
CATEGORY_DIRS = dict(CATEGORY_TITLES)
CATEGORY_DIRS["unknown"] = "未识别"


EXCEL_EXT = (".xlsx", ".xlsm", ".xls")


def scan_headers(path, max_rows=15, max_cells=60, log=None):
    """保留原扫描入口，具体格式分支由独立模块维护。"""

    return library_scan.scan_headers(path, max_rows, max_cells, log)


def _score_sheet(fname, tokens, ext):
    """委托独立规则模块计算单页签分数，保留原有内部调用接口。"""
    return score_sheet(fname, tokens, ext)

# 分类分数达到 50 才自动归档到业务类别；较低结果保留原始分但进入“未识别”。
ACCEPT_THRESHOLD = 50


def classify(path, log=None):
    """
    对一个文件的全部页签评分，返回主类别、多标签、可信度、信号和页签映射。

    每个类别分别保留得分最高的页签，因此一个工作簿可以同时作为多个业务模块的数据源；
    物理主类别取全局最高分，用于决定归档目录。最高分低于阈值时归为未识别，仍返回
    原始分和信号供管理员判断是否需要手动改类或完善规则。
    """
    ext = os.path.splitext(path)[1].lower()
    fname = os.path.basename(path)
    sheets = scan_headers(path, log=log)
    if not sheets:
        # 文件名信号仍可能提供有限评分；使用一个空页签占位而不是直接跳过分类。
        sheets = {"": set()}
    best = {"category": UNKNOWN, "score": 0, "signals": [], "sheet": ""}
    # 每类别保留最佳页签，支持同一工作簿的不同页签服务不同业务功能。
    per_cat = {}  # category -> {score, signals, sheet}。
    for sname, tokens in sheets.items():
        scored = _score_sheet(fname, tokens, ext)
        for cat, (sc, sig) in scored.items():
            if sc > best["score"]:
                # 同分时保留更早遍历的页签和类别，保证分类结果稳定可复现。
                best = {"category": cat, "score": sc, "signals": sig, "sheet": sname}
            if cat not in per_cat or sc > per_cat[cat]["score"]:
                per_cat[cat] = {"score": sc, "signals": sig, "sheet": sname}
    if best["score"] < ACCEPT_THRESHOLD:
        conf = int(best["score"])  # 未过阈值仍保留原始分，方便人工分析接近程度。
        return {"category": UNKNOWN, "confidence": conf, "categories": [],
                "signals": best["signals"], "sheet": best["sheet"], "sheets": {}}
    # 所有过阈值类别作为标签按分数降序；主类别仍由全局最高分决定。
    labels = sorted((c for c, v in per_cat.items() if v["score"] >= ACCEPT_THRESHOLD),
                    key=lambda c: per_cat[c]["score"], reverse=True)
    # 保存“类别 -> 最佳页签”，业务模块从数据库选文件后可直接定位正确数据页。
    sheet_map = {c: per_cat[c]["sheet"] for c in labels}
    return {"category": best["category"], "confidence": min(100, int(best["score"])),
            "signals": best["signals"], "sheet": best["sheet"],
            "categories": labels, "sheets": sheet_map}


# ---------------- 索引读写 ----------------
def _load_index():
    """
    读取本机文件库 JSON 索引；缺失、损坏或根结构不合法时返回空索引。

    此函数是底层读取助手，不自动删除或重建归档文件。损坏索引回落空值可保持界面可用，
    但正式写操作都在文件锁内进行，降低正常运行中产生损坏的概率。
    """
    p = paths.library_index_path()
    if not os.path.isfile(p):
        return {"items": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {"items": []}
    return {"items": []}


def _save_index(idx):
    """
    使用同目录临时文件、刷新落盘和 ``os.replace`` 原子更新索引，成功返回真值。

    临时文件与正式索引位于同一文件系统，替换不会暴露半写 JSON。失败时尽力清理临时
    文件并返回假值，由调用方联动回滚归档文件，避免索引和磁盘状态分离。
    """
    p = paths.library_index_path()
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                # 尽力把 JSON 刷到磁盘再替换，减少断电后只存在目录项但内容未落盘的风险。
                os.fsync(f.fileno())
            except OSError:
                # 某些文件系统不支持 fsync，原子替换仍可继续，不能因此完全禁止导入。
                pass
        os.replace(tmp, p)
        return True
    except Exception:
        # 保存错误由调用方转成业务错误；此处只负责不残留临时索引。
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def _cat_dir(category):
    """解析分类对应的中文归档目录并确保它存在。"""
    d = os.path.join(paths.library_dir(), CATEGORY_DIRS.get(category, category))
    paths._ensure(d)
    return d


def _now_str():
    """返回本地分钟级更新时间文本，用于索引排序与界面展示。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def list_items(category=None):
    """
    返回全部索引条目，或筛选主类别及附加标签中命中指定类别的条目。

    旧索引只有单个 ``category`` 字段，筛选时兼容回退；返回顺序保持索引顺序，由需要
    时间排序的调用方显式处理，避免基础函数暗中改变界面稳定性。
    """
    items = _load_index()["items"]
    if category:
        # 多标签文件在任一相关业务选择器中都应可见，物理归档位置不影响逻辑可见性。
        items = [it for it in items
                 if category in (it.get("categories") or [it.get("category")])]
    return items


def _item_cats(it):
    """返回条目全部类别标签；旧索引没有多标签字段时退回主类别。"""
    return it.get("categories") or [it.get("category", UNKNOWN)]


def counts():
    """统计每个类别的可见条目数；多标签文件在每个标签下各计一次。"""
    c = {cat: 0 for cat in CATEGORIES}
    c[UNKNOWN] = 0
    for it in _load_index()["items"]:
        for cat in _item_cats(it):
            c[cat] = c.get(cat, 0) + 1
    return c


def storage_stats():
    """返回索引在册条目数及其当前真实文件大小总和。

    只统计索引在册的归档表（count 与 size 始终一致）；孤立残留文件不计入，
    避免出现"0 张表却占用 X MB"这类自相矛盾的展示。"""
    items = _load_index()["items"]
    total = 0
    for it in items:
        p = it.get("path", "")
        try:
            if p and os.path.isfile(p):
                total += os.path.getsize(p)
        except OSError:
            # 单个文件暂时不可访问时跳过大小，不影响其他条目和文件数量展示。
            pass
    return len(items), total


def human_size(nbytes):
    """按 1024 进位把字节数格式化为 B、KB、MB 或 GB 的简短界面文本。"""
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return "%.1f GB" % n


def import_file(path, log=None):
    """
    分类并复制归档单个文件，返回含分类、可信度、页签和来源信息的索引条目。

    同一主类别下同名文件视为新版：覆盖前先复制为 ``.bak``；新内容先写 ``.part``，
    再原子替换正式归档。归档与索引更新均在同一文件锁内，任一步失败都会恢复旧文件
    或删除本次新文件。源文件从不删除，是否清理上传临时文件由调用方决定。
    """
    info = classify(path, log=lambda message: library_storage.safe_log(log, message))
    cat = info["category"]
    fname = os.path.basename(path)
    dst_dir = _cat_dir(cat)
    dst = os.path.join(dst_dir, fname)

    # 文件锁覆盖索引读改写和归档替换，避免并发任务互相覆盖 items 列表或同名文件。
    with file_lock(paths.library_index_path()):
        idx = _load_index()
        replaced, bak = library_storage.prepare_import_backup(dst)
        items = library_storage.without_same_primary_item(idx["items"], cat, fname)
        part = dst + ".part"
        try:
            # 临时文件与目标同目录，os.replace 才能提供同文件系统内的原子提交。
            shutil.copy2(path, part)
            os.replace(part, dst)
            item = library_storage.build_library_item(path, dst, info, _now_str())
            items.append(item)
            idx["items"] = items
            if _save_index(idx) is False:
                raise IOError("索引保存失败")
        except Exception:
            library_storage.rollback_import(part, dst, bak, replaced)
            raise IOError("索引或归档保存失败，已回滚：%s" % fname)
    library_storage.safe_log(
        log,
        "%s → 【%s】可信度 %d%s"
        % (
            fname,
            CATEGORY_TITLES.get(cat, cat),
            info["confidence"],
            "（替换旧版）" if replaced else "",
        ),
    )
    return item


def import_many(pathlist, log=None):
    """逐个导入文件并返回成功条目；单个失败记录日志后继续处理其余文件。"""
    out = []
    for p in pathlist:
        try:
            out.append(import_file(p, log=log))
        except Exception as e:
            # 文件之间相互独立，一个损坏文件不应阻止同批其他有效资料进入数据库。
            library_storage.safe_log(log, "导入失败 %s：%s" % (os.path.basename(p), e))
    return out


def remove_item(category, name, delete_file=True):
    """
    从索引移除指定类别可见且名称匹配的条目，并按需删除归档及其备份。

    先在锁内保存新索引，成功后才删除文件；若索引保存失败，磁盘文件保持不动，避免
    出现无法通过界面恢复的孤立删除。多标签条目在任一标签下执行删除都会移除整个条目，
    因为它在磁盘上只有一份物理归档。
    """
    with file_lock(paths.library_index_path()):
        idx = _load_index()
        keep, gone = library_storage.partition_items(idx["items"], category, name)
        idx["items"] = keep
        if gone and _save_index(idx) is False:
            raise IOError("数据库索引保存失败，未删除归档文件")
        if delete_file:
            # 必须先原子提交索引，再处理可失败的物理文件清理。
            library_storage.delete_item_files(gone)
        return len(gone)


def reclassify(category, name, new_category):
    """
    把一个索引条目人工改判为单一新类别，同时移动物理归档并原子更新索引。

    人工指定会清除旧的自动多标签，将可信度设为 100 并记录人工信号。目标目录存在同名
    文件时先改名备份，索引保存成功后才删除该备份；任一步失败则把新文件移回源位置，
    并恢复目标原文件，尽量保持改类前状态。
    """
    if new_category not in CATEGORIES and new_category != UNKNOWN:
        return False
    with file_lock(paths.library_index_path()):
        idx = _load_index()
        item = library_storage.matching_item(idx["items"], category, name)
        if item is None:
            return False
        source = item.get("path", "")
        if not source or not os.path.isfile(source):
            # 缺失源文件时拒绝只改索引，防止产生界面可见但无法打开的幽灵条目。
            return False
        destination = os.path.join(_cat_dir(new_category), name)
        original_item = dict(item)
        moved = False
        backup = None
        try:
            moved, backup = library_storage.move_for_reclassification(source, destination)
            library_storage.set_manual_category(item, new_category, destination, _now_str())
            if _save_index(idx) is False:
                raise IOError("索引保存失败")
            library_storage.discard_reclassify_backup(backup)
            return True
        except Exception:
            library_storage.rollback_reclassification(source, destination, moved, backup)
            # 即使索引尚未落盘，也恢复当前内存对象，避免同一调用链继续看到半更新字段。
            item.clear()
            item.update(original_item)
            return False


def latest_in(category):
    """按索引更新时间降序返回指定类别最新归档路径；没有条目时返回 ``None``。"""
    items = sorted(list_items(category), key=lambda x: x.get("updated", ""), reverse=True)
    return items[0]["path"] if items else None
