# -*- coding: utf-8 -*-
"""日清看板的参会人员与生产班组考勤归一化。

本模块负责把两种不同的考勤模型投影为看板共用的汇总结构：参会人员按姓名逐人统计，
生产人员按班组和班次统计编制、出勤与差异。模块仅补齐旧快照缺失的派生字段，不覆盖
管理员确认值；生产差异允许为负数，以真实反映临时支援造成的超编出勤。所有原始数据
仍保留在快照中，本模块不执行数据库写入。"""

from __future__ import annotations

from typing import Any, Mapping

from .daily_report_values import integer, text


def _new_unit_summary(person_type: str, unit: str, shift: str) -> dict[str, object]:
    """创建逐人考勤的单位/班次汇总行。"""

    return {
        "person_type": person_type,
        "unit": unit,
        "shift": shift,
        "total": 0,
        "present": 0,
        "absent": 0,
        "difference": 0,
        "reasons": [],
    }


def attendance_unit_summary(people: object) -> list[dict[str, object]]:
    """按人员类型、单位和班次生成参会人员考勤汇总。"""

    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    source_people = people if isinstance(people, list) else []
    for person in source_people:
        if not isinstance(person, Mapping):
            continue
        person_type = text(person.get("person_type")) or "participant"
        unit = text(person.get("unit")).strip() or "未填写单位/班组"
        shift = text(person.get("shift")).strip() or "未填写班次"
        key = (person_type, unit, shift)
        target = grouped.setdefault(key, _new_unit_summary(person_type, unit, shift))
        target["total"] = int(target["total"]) + 1
        if bool(person.get("present")):
            target["present"] = int(target["present"]) + 1
            continue
        target["absent"] = int(target["absent"]) + 1
        reason = text(person.get("reason")).strip()
        if reason:
            # reasons 由本模块创建为 list；显式局部变量让类型和追加目标更清楚。
            reasons = target["reasons"]
            if isinstance(reasons, list):
                reasons.append(f"{text(person.get('name')) or '未填写姓名'}：{reason}")
    rows = list(grouped.values())
    for row in rows:
        # 逐人考勤的编制等于名册人数，所以编制差异就是缺勤人数。
        row["difference"] = int(row["absent"])
    return sorted(
        rows,
        key=lambda row: (
            0 if row["person_type"] == "participant" else 1,
            str(row["unit"]),
            str(row["shift"]),
        ),
    )


def _production_groups(result: dict[str, object]) -> list[Mapping[str, Any]]:
    """取得有效班组班次行，并把非法旧值修正为空列表。"""

    raw_groups = result.get("production_groups")
    if not isinstance(raw_groups, list):
        raw_groups = []
        result["production_groups"] = raw_groups
    # 返回值只用于派生统计；原列表仍保留在快照中，历史字段不会被重写。
    return [item for item in raw_groups if isinstance(item, Mapping)]


def _apply_production_defaults(
    result: dict[str, object],
    groups: list[Mapping[str, Any]],
) -> None:
    """仅补齐旧快照缺失的生产考勤派生字段，不覆盖管理员确认值。"""

    result.setdefault(
        "production_group_count",
        len({item.get("group_id") for item in groups if item.get("group_id") is not None}),
    )
    result.setdefault("production_shift_count", len(groups))
    result.setdefault(
        "production_present_count",
        sum(integer(item.get("attendance_count")) for item in groups),
    )
    result.setdefault(
        "production_staffing_count",
        sum(integer(item.get("staffing_count")) for item in groups),
    )
    result.setdefault("production_total", result["production_staffing_count"])
    # 差异允许为负数，以真实暴露临时支援造成的实际出勤超过编制。
    result.setdefault(
        "production_difference",
        integer(result.get("production_staffing_count"))
        - integer(result.get("production_present_count")),
    )
    # 短缺人数只累计正差异，超编出勤不能抵消另一个班次的缺员。
    result.setdefault(
        "production_shortage_count",
        sum(max(integer(item.get("difference")), 0) for item in groups),
    )


def normalize_attendance_snapshot(
    attendance: Mapping[str, Any] | None,
) -> dict[str, object]:
    """补齐生产班组派生指标，并兼容只有逐人考勤的旧快照。"""

    result = dict(attendance or {})
    base_defaults = {
        "people": [],
        "present_count": 0,
        "absent_count": 0,
        "participant_present_count": 0,
        "participant_absent_count": 0,
        "participant_total": 0,
        "production_groups": [],
    }
    for key, value in base_defaults.items():
        result.setdefault(key, value)
    groups = _production_groups(result)
    _apply_production_defaults(result, groups)
    result.setdefault("unit_summary", attendance_unit_summary(result.get("people")))
    return result


__all__ = ["attendance_unit_summary", "normalize_attendance_snapshot"]
