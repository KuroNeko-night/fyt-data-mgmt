# -*- coding: utf-8 -*-
"""日清看板的现场问题字段规范化与分类统计。"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from . import workshop_issue_core
from .daily_report_values import text


def normalize_workshop_issue(
    issue: Mapping[str, Any],
    report_date: str,
) -> dict[str, object]:
    """把五类现场问题转换为看板和报表共用的稳定字段集合。"""

    images = issue.get("images") if isinstance(issue.get("images"), list) else []
    uploader = issue.get("uploader") if isinstance(issue.get("uploader"), Mapping) else {}
    resolved_by = issue.get("resolved_by") if isinstance(issue.get("resolved_by"), Mapping) else {}
    # 历史类别名称统一交给现场问题 Core 归一化；本模块不复制模板别名规则。
    category = workshop_issue_core.normalize_workshop_category(issue.get("category"), issue)
    # 除明确的 resolved 外一律按处理中展示，未知历史状态不能被误判为已闭环。
    resolution_status = "resolved" if text(issue.get("resolution_status")) == "resolved" else "open"
    return {
        "id": text(issue.get("id")),
        "issue_date": report_date,
        "cause": text(issue.get("cause")),
        "primary_owner": text(issue.get("primary_owner")).strip() or "未填写",
        "secondary_owner": text(issue.get("secondary_owner")),
        "notes": text(issue.get("notes")),
        "category": category,
        "severity": text(issue.get("severity")) or "normal",
        "issue_source": text(issue.get("issue_source")),
        "model": text(issue.get("model")),
        "country": text(issue.get("country")),
        "batch_no": text(issue.get("batch_no")),
        "team": text(issue.get("team")),
        "material_code": text(issue.get("material_code")),
        "material_name": text(issue.get("material_name")),
        "cause_analysis": text(issue.get("cause_analysis")),
        "corrective_action": text(issue.get("corrective_action")),
        "responsibility_party": text(issue.get("responsibility_party")),
        "external_inspection_owner": text(issue.get("external_inspection_owner")),
        "discoverer": text(issue.get("discoverer")),
        "issue_level": text(issue.get("issue_level")),
        "quantity": text(issue.get("quantity")),
        "issue_type": text(issue.get("issue_type")),
        "completion_date": text(issue.get("completion_date")),
        "recurring": text(issue.get("recurring")),
        "record_count": text(issue.get("record_count")),
        "happened_at": text(issue.get("happened_at")),
        "handling_time": text(issue.get("handling_time")),
        "responsible_person": text(issue.get("responsible_person")),
        "updated_by_name": text(issue.get("updated_by_name")),
        "carrier": text(issue.get("carrier")),
        "supplier": text(issue.get("supplier")),
        "tracking_status": text(issue.get("tracking_status")),
        "resolution_status": resolution_status,
        "resolution_note": text(issue.get("resolution_note")),
        "resolved_at": text(issue.get("resolved_at")),
        "resolved_by_name": text(resolved_by.get("display_name") or issue.get("resolved_by_name")),
        "created_at": text(issue.get("created_at")),
        "updated_at": text(issue.get("updated_at")),
        # 新接口返回嵌套账号，旧快照只有 uploader_name；按新到旧回退以兼容历史数据。
        "uploader": text(uploader.get("display_name") or uploader.get("username"))
        or text(issue.get("uploader_name"))
        or "未知账号",
        "images": images,
        "image_count": len(images),
    }


def _distribution(
    counter: Counter[str],
    key: str,
) -> list[dict[str, object]]:
    """把计数器转换为数量降序、名称升序的稳定分布列表。"""

    return [
        {key: name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_workshop_snapshot(
    workshop_issues: list[Mapping[str, Any]],
    report_date: str,
) -> dict[str, object]:
    """聚合现场问题数量、解决状态、负责人和模板分类分布。"""

    issues = [normalize_workshop_issue(issue, report_date) for issue in workshop_issues]
    owners = Counter(str(issue["primary_owner"]) for issue in issues)
    categories = Counter(str(issue["category"]) for issue in issues)
    resolved_count = sum(issue["resolution_status"] == "resolved" for issue in issues)
    return {
        "issue_count": len(issues),
        "open_count": len(issues) - resolved_count,
        "resolved_count": resolved_count,
        "image_count": sum(int(issue["image_count"]) for issue in issues),
        "owner_count": len(owners),
        "owner_distribution": _distribution(owners, "owner"),
        "category_distribution": _distribution(categories, "category"),
        "issues": issues,
    }


__all__ = ["build_workshop_snapshot", "normalize_workshop_issue"]
