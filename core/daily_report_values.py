# -*- coding: utf-8 -*-
"""日清快照跨业务域共用的轻量值规范化工具。

该模块只处理值类型，不了解数据库、到料、考勤或现场问题结构。把这些基础转换从
``daily_report_snapshot`` 抽离后，各业务聚合器可以单独测试和维护，同时 Excel 导出
仍能通过快照模块的兼容别名复用同一口径。
"""

from __future__ import annotations

from datetime import datetime


def text(value: object) -> str:
    """把任意值转换为可安全展示的文本，空值统一为空字符串。"""

    # 不能直接使用 ``str(None)``，否则前端和 Excel 会出现没有业务意义的 ``None``。
    return "" if value is None else str(value)


def integer(value: object) -> int:
    """把松散输入转换为整数，无法转换时按零参与计数汇总。"""

    try:
        return int(value)
    except (TypeError, ValueError):
        # 日清数据可能包含历史空串或人工录入脏值；单项无效不应中断整份管理报告。
        return 0


def number(value: object) -> float | None:
    """解析数量文本；没有可靠数值时返回 ``None``，与真实数值零明确区分。"""

    if value in (None, "") or isinstance(value, bool):
        # bool 是 int 的子类，但业务数量中的 True/False 不能被误计为 1/0。
        return None
    try:
        # 人工上传成品表常带千分位逗号，先移除再交给 float 做完整格式校验。
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def normalized_number(value: object) -> int | float:
    """将数量规范成整数或最多四位小数，脏值按零返回。"""

    parsed = number(value)
    if parsed is None:
        return 0
    return int(parsed) if parsed.is_integer() else round(parsed, 4)


def validate_date(value: object) -> str:
    """严格校验日清业务日期，并返回 ``YYYY-MM-DD``。"""

    raw = text(value).strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        # 严格拒绝不存在的日期，避免查询日期、文件名和月度台账切片彼此错位。
        raise ValueError("日清报告日期必须是 YYYY-MM-DD") from exc


__all__ = ["integer", "normalized_number", "number", "text", "validate_date"]
