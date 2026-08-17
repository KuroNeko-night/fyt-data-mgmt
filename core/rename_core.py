# -*- coding: utf-8 -*-
"""
批量文件重命名核心
==================
根据一组明确规则先生成只读预览计划，检查非法名称、本批重名和磁盘目标冲突；只有
用户确认后才执行 ``status == "ok"`` 的项目。实际改名使用“源文件 -> 唯一临时名 ->
最终目标名”两阶段流程，能够安全处理 A 改 B、B 改 A 以及更长的链式交换。

成功结果返回“最终路径 -> 原始路径”撤销映射，撤销同样使用两阶段流程。任一阶段失败
都会尽力回滚；若目标改名和回滚同时失败，错误中保留遗留临时文件的完整路径，便于
人工恢复，不静默丢失文件。

规则 RenameRule 字段：
  find / replace        : 在主名(不含扩展名)里查找替换；find 为空则跳过
  use_regex             : 查找替换是否按正则(默认否，纯文本)
  prefix / suffix       : 主名前/后追加(suffix 加在扩展名之前)
  base_name             : 非空时整体替换主名(常配合序号，如 "考勤表")
  seq_enabled           : 是否追加序号
  seq_start / seq_digits: 序号起始值 / 位数(补零)
  seq_sep               : 序号与主名之间的分隔符
  ext_lower             : 是否把扩展名转小写

本模块只使用标准库，不自行弹窗，也不递归扫描目录。文件列表顺序决定序号，界面必须
把完整预览交给用户确认后再调用执行入口。
"""
import os
import re


class RenameRule(object):
    """一组可组合的文件主名、序号和扩展名变换规则。"""

    def __init__(self, find="", replace="", use_regex=False,
                 prefix="", suffix="", base_name="",
                 seq_enabled=False, seq_start=1, seq_digits=3, seq_sep="_",
                 ext_lower=False):
        """保存规则参数，不在构造阶段访问文件系统或校验正则。"""
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
        """判断规则是否不会改变任何名称，供界面在预览前提示。"""
        return not any((self.find, self.prefix, self.suffix, self.base_name,
                        self.seq_enabled, self.ext_lower))


def _new_filename(old_name, rule, index):
    """纯计算单个目标文件名，``index`` 为本批次 0 基顺序。

    处理顺序固定为：拆分主名/扩展名、可选扩展名小写、整体主名替换或查找替换、追加
    序号、包裹前后缀、拼回扩展名。``base_name`` 与 ``find`` 互斥，整体替换优先。
    非法正则在此保持原主名，界面可通过预先校验提示用户；函数不接触磁盘。
    """
    stem, ext = os.path.splitext(old_name)
    if rule.ext_lower:
        ext = ext.lower()
    # 整体主名常与序号组合成“考勤表_001”，因此优先于局部查找替换。
    if rule.base_name:
        stem = rule.base_name
    # 未指定统一主名时才执行纯文本或正则替换。
    elif rule.find:
        if rule.use_regex:
            try:
                stem = re.sub(rule.find, rule.replace, stem)
            except re.error:
                pass  # 名称计算保持无异常；界面规则校验负责向用户解释错误。
        else:
            stem = stem.replace(rule.find, rule.replace)
    # 序号位数至少为一，超过指定位数时 Python 会自然扩展而不会截断数字。
    if rule.seq_enabled:
        num = rule.seq_start + index
        digits = max(1, int(rule.seq_digits))
        stem = "%s%s%0*d" % (stem, rule.seq_sep, digits, num)
    # 后缀属于主名，始终放在扩展名之前。
    stem = "%s%s%s" % (rule.prefix, stem, rule.suffix)
    return stem + ext


# Windows 文件名非法字符与设备保留名；比较保留名时不区分大小写。
_ILLEGAL = set('\\/:*?"<>|')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} \
            | {"LPT%d" % i for i in range(1, 10)}


def _name_invalid(name):
    """检查名称是否违反 Windows 单个文件名约束。

    禁止空名、相对目录符号、非法字符、尾部空格/点以及 CON、COM1 等设备保留名。
    这里只验证单个名称，不检查完整路径长度和磁盘冲突，后者由预览计划处理。
    """
    if not name or name in (".", ".."):
        return True
    if any(c in _ILLEGAL for c in name):
        return True
    # Windows 会静默裁掉尾部空格/点，若放行会导致预览名称和实际落盘名称不一致。
    if name.rstrip(" .") != name:
        return True
    stem = os.path.splitext(name)[0].upper().rstrip(" .")
    return stem in _RESERVED


class PlanItem(object):
    """一条重命名预览，包含原路径、目标名称、状态和客户可读说明。"""

    def __init__(self, old_path, new_name, status, note=""):
        """根据原路径和目标名称计算同目录目标路径。"""
        self.old_path = old_path
        self.old_name = os.path.basename(old_path)
        self.new_name = new_name
        self.new_path = os.path.join(os.path.dirname(old_path), new_name) \
            if new_name else ""
        self.status = status
        self.note = note

    @property
    def will_change(self):
        """仅当状态为 ``ok`` 时表示该项会被执行。"""
        return self.status == "ok"


def _plan_items(paths, rule):
    """第一轮计算单项状态；序号严格使用原输入顺序，包括最终被阻止的项目。"""
    items = []
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
    return items


def _mark_duplicate_targets(items):
    """第二轮检查本批次目标碰撞；把整组都标记 dup，避免任意选择其中一个执行。"""
    seen = {}
    for it in items:
        if it.status != "ok":
            continue
        key = it.new_path.lower()
        seen.setdefault(key, []).append(it)
    for group in seen.values():
        if len(group) > 1:
            for it in group:
                it.status = "dup"
                it.note = "与本批次其它文件重名"


def _mark_existing_targets(items, paths):
    """第三轮检查磁盘已有目标；本批源路径集合使用绝对规范路径消除写法差异。"""
    sources = set(os.path.normcase(os.path.abspath(p)) for p in paths)
    for it in items:
        if it.status != "ok":
            continue
        tgt = os.path.normcase(os.path.abspath(it.new_path))
        if os.path.exists(it.new_path) and tgt not in sources:
            it.status = "exists"
            it.note = "目标已存在于该文件夹"


def build_plan(paths, rule):
    """根据输入顺序生成预览计划，并执行所有可提前判断的冲突检查。

    冲突检测：
      · empty/invalid : 新名为空或非法字符/保留名
      · same          : 新名与原名一致(不需重命名)
      · dup           : 本批次内多个文件算出同一目标(同目录)
      · exists        : 目标已存在于磁盘，且不是文件自身/本批次将被改走的源
    目标比较按 Windows 大小写不敏感规则执行。磁盘冲突检查允许目标正好是本批次的某个
    源文件，因为两阶段执行会先把所有源移到临时名；其他已存在目标一律阻止。函数只
    查询文件是否存在，不执行写操作。
    """
    items = _plan_items(paths, rule)
    _mark_duplicate_targets(items)
    _mark_existing_targets(items, paths)
    return items


def summarize(items):
    """统计各预览状态、总数和真正阻塞项数量。

    ``same`` 代表无需处理而非错误，因此不计入 ``blocked``；未知状态仍会动态计数，
    但固定阻塞合计只包含当前四类错误状态。
    """
    s = {"ok": 0, "same": 0, "empty": 0, "invalid": 0, "dup": 0, "exists": 0}
    for it in items:
        s[it.status] = s.get(it.status, 0) + 1
    s["total"] = len(items)
    s["blocked"] = s["empty"] + s["invalid"] + s["dup"] + s["exists"]
    return s


def apply_plan(items, log=None):
    """两阶段执行计划中的可改名项，并返回成功数、失败和撤销映射。

    第一阶段尽量把每个源移动到同目录临时名；单项失败不阻止其他项。第二阶段从临时名
    移到目标名，失败时先尝试恢复原名。只有成功到达目标的项目进入撤销映射
    ``[(最终路径, 原始路径)]``。临时名使用对象 ID 降低同批碰撞概率且保持同盘改名。
    """

    def _log_message(m):
        """仅在调用方提供日志回调时转发状态文本。"""
        if log:
            log(m)

    todo = [it for it in items if it.status == "ok"]
    done_undo = []  # 只记录已经到达最终路径的项目。
    failed = []     # 使用名称和原因供界面逐条展示。

    # 第一阶段把所有可移动源腾空，后续目标即使原来是另一源文件也不会冲突。
    stage = []  # (临时路径, 目标路径, 原路径)
    for it in todo:
        d = os.path.dirname(it.old_path)
        tmp = os.path.join(d, "__renaming_%d__%s" % (id(it), it.new_name))
        try:
            os.rename(it.old_path, tmp)
            stage.append((tmp, it.new_path, it.old_path))
        except OSError as e:
            failed.append((it.old_name, str(e)))
            _log_message("跳过 %s：%s" % (it.old_name, e))

    # 第二阶段提交最终名称；每个失败项目独立回滚，不撤销已经成功的其他项目。
    for tmp, tgt, origin in stage:
        try:
            os.rename(tmp, tgt)
            done_undo.append((tgt, origin))
            _log_message("%s → %s" % (os.path.basename(origin), os.path.basename(tgt)))
        except OSError as e:
            # 目标失败后优先恢复原名，避免用户目录遗留内部临时文件。
            try:
                os.rename(tmp, origin)
                failed.append((os.path.basename(origin), str(e)))
                _log_message("失败 %s：%s" % (os.path.basename(origin), e))
            except OSError as e2:
                # 双重故障时不能再猜测安全目标，保留临时文件并把完整位置交给人工恢复。
                failed.append((os.path.basename(tmp),
                               "改名失败且回滚失败,遗留临时文件:%s(原名 %s;%s / %s)"
                               % (tmp, os.path.basename(origin), e, e2)))
                _log_message("严重:%s 遗留临时文件 %s(回滚亦失败:%s)"
                    % (os.path.basename(origin), tmp, e2))

    return len(done_undo), failed, done_undo


def undo(undo_map, log=None):
    """按 ``apply_plan`` 返回的映射两阶段还原文件名。

    当前文件不存在时只记录失败；第一阶段先腾空所有最终名称，第二阶段恢复原始路径。
    第二阶段失败时尽力把临时文件放回撤销前的当前名称，防止撤销操作制造孤儿文件。
    返回成功还原数和逐项失败列表。
    """

    def _log_message(m):
        """在存在日志回调时报告成功还原。"""
        if log:
            log(m)

    ok = 0
    failed = []
    stage = []  # (临时路径, 原始路径, 当前路径)
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
            _log_message("还原 %s → %s" % (os.path.basename(cur), os.path.basename(origin)))
        except OSError as e:
            try:
                # 恢复原名失败时先退回撤销前名称；二次失败则保留临时文件供人工处理。
                os.rename(tmp, cur)
            except OSError:
                pass
            failed.append((os.path.basename(origin), str(e)))
    return ok, failed
