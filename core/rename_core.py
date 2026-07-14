# -*- coding: utf-8 -*-
"""
批量重命名核心 —— 纯标准库、零依赖、可预览、可撤销
====================================================
办公通用小工具：按规则批量改文件名，先算好"新名"给页面预览(含冲突检测)，
确认后再落盘。落盘用"两段式(先改临时名再改目标名)"，规避 A→B、B→A 这类
交换/链式冲突。返回撤销映射，供页面一键还原。

规则 RenameRule 字段：
  find / replace        : 在主名(不含扩展名)里查找替换；find 为空则跳过
  use_regex             : 查找替换是否按正则(默认否，纯文本)
  prefix / suffix       : 主名前/后追加(suffix 加在扩展名之前)
  base_name             : 非空时整体替换主名(常配合序号，如 "考勤表")
  seq_enabled           : 是否追加序号
  seq_start / seq_digits: 序号起始值 / 位数(补零)
  seq_sep               : 序号与主名之间的分隔符
  ext_lower             : 是否把扩展名转小写

兼容 Windows 7 + Python 3.8。
"""
import os
import re


class RenameRule(object):
    """一组重命名规则。字段含义见模块文档。"""

    def __init__(self, find="", replace="", use_regex=False,
                 prefix="", suffix="", base_name="",
                 seq_enabled=False, seq_start=1, seq_digits=3, seq_sep="_",
                 ext_lower=False):
        self.find = find
        self.replace = replace
        self.use_regex = use_regex
        self.prefix = prefix
        self.suffix = suffix
        self.base_name = base_name
        self.seq_enabled = seq_enabled
        self.seq_start = seq_start
        self.seq_digits = seq_digits
        self.seq_sep = seq_sep
        self.ext_lower = ext_lower

    def is_noop(self):
        """规则是否为空(什么都不改)——页面据此提示用户。"""
        return not any((self.find, self.prefix, self.suffix, self.base_name,
                        self.seq_enabled, self.ext_lower))


def _new_filename(old_name, rule, index):
    """根据规则算出单个文件的新文件名(仅名字，不含目录)。index 从 0 起用于序号。

    处理顺序：拆分主名/扩展名 → (整体替换)base_name → 查找替换 → 前后缀 → 序号 → 扩展名。
    顺序固定且可预测，页面提示区会向用户说明。"""
    stem, ext = os.path.splitext(old_name)
    if rule.ext_lower:
        ext = ext.lower()
    # 整体替换主名(如批量改成统一基名)
    if rule.base_name:
        stem = rule.base_name
    # 查找替换(纯文本或正则)
    elif rule.find:
        if rule.use_regex:
            try:
                stem = re.sub(rule.find, rule.replace, stem)
            except re.error:
                pass                        # 正则非法：本项不改，页面另有校验提示
        else:
            stem = stem.replace(rule.find, rule.replace)
    # 序号
    if rule.seq_enabled:
        num = rule.seq_start + index
        digits = max(1, int(rule.seq_digits))
        stem = "%s%s%0*d" % (stem, rule.seq_sep, digits, num)
    # 前后缀(后缀加在扩展名之前)
    stem = "%s%s%s" % (rule.prefix, stem, rule.suffix)
    return stem + ext


# Windows 文件名非法字符 与 保留名
_ILLEGAL = set('\\/:*?"<>|')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} \
            | {"LPT%d" % i for i in range(1, 10)}


def _name_invalid(name):
    """新文件名是否非法(空、含非法字符、Windows 保留名)。"""
    if not name or name in (".", ".."):
        return True
    if any(c in _ILLEGAL for c in name):
        return True
    stem = os.path.splitext(name)[0].upper().rstrip(" .")
    return stem in _RESERVED


class PlanItem(object):
    """预览计划里的一行。status: ok/same/empty/invalid/dup/exists。"""

    def __init__(self, old_path, new_name, status, note=""):
        self.old_path = old_path
        self.old_name = os.path.basename(old_path)
        self.new_name = new_name
        self.new_path = os.path.join(os.path.dirname(old_path), new_name) \
            if new_name else ""
        self.status = status
        self.note = note

    @property
    def will_change(self):
        return self.status == "ok"


def build_plan(paths, rule):
    """把 [路径...] + 规则 算成预览计划 [PlanItem...]，纯计算不碰磁盘写。

    冲突检测：
      · empty/invalid : 新名为空或非法字符/保留名
      · same          : 新名与原名一致(不需重命名)
      · dup           : 本批次内多个文件算出同一目标(同目录)
      · exists        : 目标已存在于磁盘，且不是文件自身/本批次将被改走的源
    仅 status==ok 的项会被真正重命名。"""
    items = []
    # 先算每项的新名
    for i, p in enumerate(paths):
        old_name = os.path.basename(p)
        new_name = _new_filename(old_name, rule, i)
        if not new_name:
            items.append(PlanItem(p, "", "empty", "新名为空"))
        elif _name_invalid(new_name):
            items.append(PlanItem(p, new_name, "invalid", "含非法字符或为系统保留名"))
        elif new_name == old_name:
            items.append(PlanItem(p, new_name, "same", "无变化"))
        else:
            items.append(PlanItem(p, new_name, "ok"))

    # 批次内重复目标(同目录同名)——大小写不敏感，贴合 Windows
    seen = {}
    for it in items:
        if it.status != "ok":
            continue
        key = it.new_path.lower()
        seen.setdefault(key, []).append(it)
    for key, group in seen.items():
        if len(group) > 1:
            for it in group:
                it.status = "dup"
                it.note = "与本批次其它文件重名"

    # 与磁盘已存在文件冲突(排除自身与本批次会被改走的源)
    sources = set(os.path.normcase(os.path.abspath(p)) for p in paths)
    for it in items:
        if it.status != "ok":
            continue
        tgt = os.path.normcase(os.path.abspath(it.new_path))
        if os.path.exists(it.new_path) and tgt not in sources:
            it.status = "exists"
            it.note = "目标已存在于该文件夹"
    return items


def summarize(items):
    """给页面用的计数概览。"""
    s = {"ok": 0, "same": 0, "empty": 0, "invalid": 0, "dup": 0, "exists": 0}
    for it in items:
        s[it.status] = s.get(it.status, 0) + 1
    s["total"] = len(items)
    s["blocked"] = s["empty"] + s["invalid"] + s["dup"] + s["exists"]
    return s


def apply_plan(items, log=None):
    """执行 status==ok 的重命名。返回 (成功数, 失败列表, 撤销映射)。

    两段式：先把每个源改成同目录下唯一临时名，再从临时名改到目标名。
    这样即便存在 A→B、B→C→A 这类链式/交换关系也不会互相踩踏。
    撤销映射为 [(最终路径, 原始路径)...]，交给 undo() 可原样还原。"""
    def _lg(m):
        if log:
            log(m)

    todo = [it for it in items if it.status == "ok"]
    done_undo = []          # (最终路径, 原路径)
    failed = []             # (原名, 原因)

    # 第一段：源 → 临时名
    stage = []              # (临时路径, 目标路径, 原路径)
    for it in todo:
        d = os.path.dirname(it.old_path)
        tmp = os.path.join(d, "__renaming_%d__%s" % (id(it), it.new_name))
        try:
            os.rename(it.old_path, tmp)
            stage.append((tmp, it.new_path, it.old_path))
        except OSError as e:
            failed.append((it.old_name, str(e)))
            _lg("跳过 %s：%s" % (it.old_name, e))

    # 第二段：临时名 → 目标名
    for tmp, tgt, origin in stage:
        try:
            os.rename(tmp, tgt)
            done_undo.append((tgt, origin))
            _lg("%s → %s" % (os.path.basename(origin), os.path.basename(tgt)))
        except OSError as e:
            # 目标失败：尽力把临时名改回原名，避免留下 __renaming__ 垃圾
            try:
                os.rename(tmp, origin)
            except OSError:
                pass
            failed.append((os.path.basename(origin), str(e)))
            _lg("失败 %s：%s" % (os.path.basename(origin), e))

    return len(done_undo), failed, done_undo


def undo(undo_map, log=None):
    """按撤销映射把文件名还原。返回 (还原数, 失败列表)。

    同样用两段式，规避还原过程中的交换/链式冲突。undo_map 为 apply_plan 的第三个返回值。"""
    def _lg(m):
        if log:
            log(m)

    ok = 0
    failed = []
    stage = []              # (临时路径, 原始路径, 当前路径)
    for cur, origin in undo_map:
        if not os.path.exists(cur):
            failed.append((os.path.basename(cur), "文件已不在原位置"))
            continue
        d = os.path.dirname(cur)
        tmp = os.path.join(d, "__undo_%d__%s" % (id(origin), os.path.basename(origin)))
        try:
            os.rename(cur, tmp)
            stage.append((tmp, origin, cur))
        except OSError as e:
            failed.append((os.path.basename(cur), str(e)))
    for tmp, origin, cur in stage:
        try:
            os.rename(tmp, origin)
            ok += 1
            _lg("还原 %s → %s" % (os.path.basename(cur), os.path.basename(origin)))
        except OSError as e:
            try:
                os.rename(tmp, cur)
            except OSError:
                pass
            failed.append((os.path.basename(origin), str(e)))
    return ok, failed
