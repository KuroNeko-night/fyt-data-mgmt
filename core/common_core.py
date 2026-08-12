# -*- coding: utf-8 -*-
"""公共业务基础设施的稳定兼容入口。

值解析和工作簿安全读取已经分别迁到 ``common_parsing`` 与 ``common_workbook``，本模块
继续导出原有名称，并集中维护人工列映射选项、输出路径和进度上报。业务模块无需修改
导入路径，也不会在考勤、对账、采购之间形成多套同名规则。
"""

from __future__ import annotations

import datetime
import os

from .common_parsing import (
    SKIP_MARKS,
    clean_str,
    day_of,
    fmt_time,
    norm_date,
    norm_name,
    num_str as _num_str,
    parse_rest,
    parse_time,
    round_half_hour,
    serial_to_date as _serial_to_date,
    to_hours,
    to_num,
)
from .common_workbook import (
    detect_uncached_formula,
    load_data_only,
    load_data_only_stream,
    load_workbook_safe as _load_workbook_safe,
    read_sheets,
    skip_pivot_cache_parse as _skip_pivot_cache_parse,
    warn_if_uncached,
)


# 标准工作时长只提供默认值；真实任务可通过 Options 由人工调整。
STANDARD_WORKDAY_HOURS = 9.0
# 工时最小单位通常为 0.5 小时，0.01 容差用于吸收浮点表示误差。
TOL = 0.01


# 每种文件类型声明列映射界面需要展示的角色，条目为（内部键、中文名、是否必填）。
ROLE_DEFS = {
    "att_source": [
        ("name", "姓名", True),
        ("date", "日期", True),
        ("on", "上班1打卡时间", True),
        ("off", "下班1打卡时间", True),
    ],
    "att_target": [
        ("name", "姓名", True),
        ("date", "日期", True),
        ("sys_on", "上班时间(系统)", False),
        ("act_on", "上班时间(实际)", False),
        ("sys_off", "下班时间(系统)", False),
        ("act_off", "下班时间(实际)", False),
        ("rest", "休息时间", False),
        ("work", "实际工作时间", False),
        ("ot", "加班", False),
    ],
    "rec_source": [
        ("name", "姓名", True),
        ("date", "日期", True),
        ("work", "实际工作时间", True),
    ],
    "rec_zong": [
        ("name", "姓名", True),
        ("comp", "所属劳务公司", False),
        ("work", "出勤工时", False),
        ("check", "对账时间", False),
    ],
    "rec_labor": [("name", "姓名", True), ("total", "合计/出勤工时列", False)],
}

KIND_TITLES = {
    "att_source": "填报·系统数据表",
    "att_target": "填报·待填考勤表",
    "rec_source": "对账·数据来源",
    "rec_zong": "对账·待对总表",
    "rec_labor": "对账·劳务对账单",
}


class Options:
    """跨考勤与工时对账流程的高级选项载体。

    ``columns`` 使用 ``{文件名: {sheet, header, data_start, roles}}`` 结构。页签和行号
    面向用户采用 Excel 的 1 基编号，角色列使用前端与配置协议约定的 0 基编号；业务
    模块在真正访问工作簿时负责一次明确转换。
    """

    def __init__(
        self,
        workday_hours=STANDARD_WORKDAY_HOURS,
        overtime=True,
        conflict="last",
        header_row=None,
        sheet_name=None,
        tolerance=TOL,
        data_start=None,
        skip_extra=None,
        columns=None,
        auto_actual=True,
        night_shift=True,
        night_start_hour=17.0,
        night_workday_hours=11.0,
        night_max_hours=16.0,
        day_max_hours=16.0,
    ):
        """规范化高级选项；无效重复策略安全回退为后者覆盖。"""

        self.workday_hours = float(workday_hours)
        self.overtime = bool(overtime)
        self.auto_actual = bool(auto_actual)
        self.night_shift = bool(night_shift)
        self.night_start_hour = float(night_start_hour)
        self.night_workday_hours = float(night_workday_hours)
        self.night_max_hours = float(night_max_hours)
        self.day_max_hours = float(day_max_hours)
        self.conflict = conflict if conflict in ("last", "first", "warn") else "last"
        self.header_row = header_row
        self.sheet_name = sheet_name or None
        self.tolerance = float(tolerance)
        self.data_start = data_start
        self.skip_extra = set(skip_extra) if skip_extra else set()
        self.columns = columns if columns else {}

    def skip_set(self):
        """返回内置与本次任务追加标记的并集，不修改模块级默认集合。"""

        return SKIP_MARKS | self.skip_extra

    def file_map(self, path):
        """按文件主名优先、完整路径兼容的顺序读取单文件映射。"""

        if not self.columns:
            return None
        # 主名方便映射跨目录复用，完整路径保留旧配置与同名文件精确区分能力。
        return self.columns.get(os.path.basename(path)) or self.columns.get(path)

    def resolve_sheet(self, path):
        """按“单文件 > 全局 > 自动”的优先级解析工作表名称。"""

        file_mapping = self.file_map(path)
        return file_mapping["sheet"] if file_mapping and file_mapping.get("sheet") else self.sheet_name

    def resolve_header(self, path):
        """按“单文件 > 全局 > 自动”解析 1 基表头行号。"""

        file_mapping = self.file_map(path)
        return file_mapping["header"] if file_mapping and file_mapping.get("header") else self.header_row

    def resolve_data_start(self, path):
        """按“单文件 > 全局 > 表头下一行”解析 1 基数据起始行。"""

        file_mapping = self.file_map(path)
        if file_mapping and file_mapping.get("data_start"):
            return file_mapping["data_start"]
        return self.data_start

    def resolve_roles(self, path):
        """返回该文件的 0 基角色列映射副本，避免调用方反向污染共享配置。"""

        file_mapping = self.file_map(path)
        return dict(file_mapping["roles"]) if file_mapping and file_mapping.get("roles") else {}

    def summary(self):
        """生成仅含业务选项的一行中文摘要，用于任务日志和人工追溯。"""

        conflict_names = {"last": "后者覆盖", "first": "先者优先", "warn": "不覆盖仅提示"}
        parts = [
            "标准工时=%g" % self.workday_hours,
            "加班=%s" % ("算" if self.overtime else "不算"),
            "重复=%s" % conflict_names.get(self.conflict, self.conflict),
            "容差=%g" % self.tolerance,
        ]
        if self.header_row:
            parts.append("表头行=%d" % self.header_row)
        if self.sheet_name:
            parts.append("工作表=%s" % self.sheet_name)
        if self.skip_extra:
            parts.append("额外假休标记=%s" % "/".join(sorted(self.skip_extra)))
        parts.append("实际时间=%s" % ("自动半小时进退位" if self.auto_actual else "不自动"))
        if self.night_shift:
            parts.append(
                "夜班=启用(≥%g点/标准%gh/上限%gh)"
                % (self.night_start_hour, self.night_workday_hours, self.night_max_hours)
            )
        else:
            parts.append("夜班=不识别")
        parts.append("白班上限=%gh" % self.day_max_hours)
        if self.columns:
            parts.append("列映射=%d个文件" % len(self.columns))
        return "；".join(parts)


DEFAULTS = Options()


def make_out_dir(src_path):
    """在源文件旁创建并返回旧版兼容 ``output`` 目录。"""

    output_dir = os.path.join(os.path.dirname(os.path.abspath(src_path)), "output")
    if not os.path.isdir(output_dir):
        # 不使用 exist_ok，若同名对象是文件，应明确失败而不是掩盖错误路径。
        os.makedirs(output_dir)
    return output_dir


def timestamp():
    """返回本地当前时间的 ``YYYYMMDD_HHMM``，供同一次任务关联命名。"""

    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def unique_path(path):
    """目标已存在时递增添加 ``(2)``、``(3)``，返回当前未占用路径。"""

    if not os.path.exists(path):
        return path
    root, extension = os.path.splitext(path)
    index = 2
    while os.path.exists(candidate := "%s (%d)%s" % (root, index, extension)):
        index += 1
    return candidate


def out_path(out_dir, base_name, suffix, ext=".xlsx", ts=None):
    """按“主名 + 后缀 + 时间戳 + 扩展名”生成唯一输出路径。"""

    task_timestamp = ts or timestamp()
    filename = "%s%s_%s%s" % (base_name, suffix, task_timestamp, ext)
    return unique_path(os.path.join(out_dir, filename))


def sheet_names(path):
    """返回工作表名列表，供人工列映射和页签选择界面使用。"""

    return [name for name, _ in read_sheets(path)]


def preview_rows(path, sheet=None, limit=8):
    """返回指定页签前若干行；页签不存在时兼容回退到第一张表。"""

    sheets = read_sheets(path)
    if not sheets:
        return None, []
    chosen = next((item for item in sheets if sheet and item[0] == sheet), sheets[0])
    name, rows = chosen
    # 复制每行，避免界面层修改预览时反向污染读取结果。
    return name, [list(row) for row in rows[:limit]]


def apply_saved_mapping(opts, path, mapping):
    """把字段映射中心命中的配置合并进 Options，显式人工设置始终优先。"""

    if opts is None or not path or not mapping:
        return False
    base_name = os.path.basename(path)
    file_mapping = dict(opts.columns.get(base_name) or {})
    for key in ("sheet", "header"):
        if mapping.get(key) and not file_mapping.get(key):
            file_mapping[key] = int(mapping[key]) if key == "header" else mapping[key]
    saved_roles = mapping.get("roles") or {}
    if saved_roles:
        merged_roles = dict(file_mapping.get("roles") or {})
        for key, value in saved_roles.items():
            # 映射存储和 Options 均使用 0 基列号，此处只规范类型，不转换列基数。
            merged_roles.setdefault(str(key), int(value))
        file_mapping["roles"] = merged_roles
    if not file_mapping:
        return False
    opts.columns[base_name] = file_mapping
    return True


def auto_apply_mapping(opts, path, role_kind):
    """依据前二十行结构查找并应用可复用字段映射。"""

    if not opts or not path:
        return None
    from . import mapping_store

    sheet, rows = preview_rows(path, sheet=opts.resolve_sheet(path), limit=20)
    mapping = mapping_store.find_for_rows(sheet, rows, role_kind)
    return mapping if mapping and apply_saved_mapping(opts, path, mapping) else None


def cell_text(value):
    """把日期或任意单元格值转换为最多十八字符的安全预览文本。"""

    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M").replace(" 00:00", "")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    value_text = str(value)
    return value_text if len(value_text) <= 18 else value_text[:17] + "…"


class Progress:
    """把阶段权重和阶段内完成比例折算成单调递增的 0～100 整数进度。"""

    def __init__(self, cb, stages):
        """保存有效回调，并预计算每个阶段的百分比起点和跨度。"""

        self._cb = cb if callable(cb) else None
        total_weight = sum(max(0, weight) for _, weight in stages) or 1
        self._span = {}
        accumulated = 0.0
        for name, weight in stages:
            fraction = max(0, weight) / total_weight * 100.0
            self._span[name] = (accumulated, fraction)
            accumulated += fraction
        self._base = 0.0
        self._range = 0.0
        self._last = -1

    def stage(self, name):
        """切换阶段并立即尝试上报该阶段起点。"""

        self._base, self._range = self._span.get(name, (self._base, 0.0))
        self._emit(self._base)

    def tick(self, i, n):
        """在当前阶段按完成量插值；负数和超额计数都会被钳制。"""

        if n and n > 0:
            fraction = min(max(i, 0), n) / float(n)
            self._emit(self._base + self._range * fraction)

    def done(self):
        """任务成功结束时把进度补到 100。"""

        self._emit(100.0)

    def _emit(self, percentage):
        """只在整数百分比严格增加时调用回调，并隔离展示层异常。"""

        if self._cb is None:
            return
        value = int(percentage)
        if value <= self._last:
            return
        self._last = value
        try:
            self._cb(value)
        except Exception:
            # 进度属于辅助展示，回调故障不能把正确完成的业务任务改成失败。
            pass


__all__ = [
    "DEFAULTS",
    "KIND_TITLES",
    "Options",
    "Progress",
    "ROLE_DEFS",
    "SKIP_MARKS",
    "STANDARD_WORKDAY_HOURS",
    "TOL",
    "apply_saved_mapping",
    "auto_apply_mapping",
    "cell_text",
    "clean_str",
    "day_of",
    "detect_uncached_formula",
    "fmt_time",
    "load_data_only",
    "load_data_only_stream",
    "make_out_dir",
    "norm_date",
    "norm_name",
    "out_path",
    "parse_rest",
    "parse_time",
    "preview_rows",
    "read_sheets",
    "round_half_hour",
    "sheet_names",
    "timestamp",
    "to_hours",
    "to_num",
    "unique_path",
    "warn_if_uncached",
]
