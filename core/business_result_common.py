# -*- coding: utf-8 -*-
"""双端业务结果投影的公共规范化与组件构造器。

本模块只处理类型兼容、动作名归一、指标、可信度、参数和明细区块，不包含任何具体
业务投影。所有明细都按列白名单裁剪，绝对路径只保留文件名。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .common_parsing import portable_basename


MAX_DETAIL_ROWS = 30
"""默认只向界面展示有限明细，完整数据仍保存在正式输出文件中。"""


def _text(value: object) -> str:
    """把展示值规范为字符串，并避免整数浮点显示成 ``1.0``。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _number(value: object, default: float = 0.0) -> float:
    """读取可计算数值；无法转换时返回调用方指定的安全默认值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: object, default: int = 0) -> int:
    """读取整数统计值，容忍旧结果中的空字符串或浮点文本。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: object) -> Mapping[str, Any]:
    """把非映射输入降级为空映射，避免历史坏结果阻断整个任务列表。"""
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    """把列表、元组等序列转换为列表，但不把字符串拆成字符数组。"""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def unwrap_result(value: object) -> Mapping[str, Any]:
    """解开 ``tauri_bridge._task`` 的信封，兼容旧 Web 任务记录。

    只有同时看到 ``result`` 映射和任务信封标记才解包；普通业务结果也可能恰好包含
    ``result`` 键，不能仅凭单字段判断。
    """
    record = _mapping(value)
    nested = record.get("result")
    envelope_keys = {"logs", "task_id", "out_dir", "presentation"}
    if isinstance(nested, Mapping) and envelope_keys.intersection(record):
        return nested
    return record


def canonical_kind(value: object) -> str:
    """把 Web/Tauri 动作名归一为稳定的投影键，并兼容历史别名。"""
    text = _text(value).strip()
    aliases = {
        "web.arrival": "arrival",
        "arrival.run": "arrival",
        "web.reconcile.review": "reconcile",
        "reconcile.run": "reconcile",
        "attendance.run": "attendance",
        "attendance_archive.run": "attendance_archive",
        "pivot.run": "pivot",
        "purchase.run": "purchase",
        "shipping_review.run": "shipping_review",
        "delivery.run": "delivery",
        "supplier_batch.run": "supplier_batch",
        "purchase_plan.run": "purchase_plan",
        "purchase_plan.diff": "purchase_diff",
        "reconcile_statement.build": "reconcile_statement",
        "invoice.generate": "invoice",
        "invoice_match.run": "invoice_match",
        "web.compare": "compare",
        "compare.run": "compare",
    }
    if text in aliases:
        return aliases[text]
    if text.startswith("web."):
        text = text[4:]
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _metric(
    key: str,
    label: str,
    value: object,
    *,
    note: str = "",
    tone: str = "neutral",
) -> dict[str, object]:
    """构造前端指标卡片；值统一转成文本，避免 React 为数字类型分支。"""
    return {
        "key": key,
        "label": label,
        "value": _text(value),
        "note": note,
        "tone": tone,
    }


def _section(
    key: str,
    title: str,
    columns: list[tuple[str, str]],
    rows: Iterable[Mapping[str, object]],
    *,
    description: str = "",
    limit: int = MAX_DETAIL_ROWS,
) -> dict[str, object]:
    """构造带列定义、总数和截断标志的明细分区。

    先按列白名单读取每行，再应用展示上限，防止原始结果中的内部字段、绝对路径或超大
    明细数组直接泄露到前端。
    """
    all_rows = [
        {column_key: _text(row.get(column_key)) for column_key, _ in columns}
        for row in rows
    ]
    safe_limit = max(1, int(limit or MAX_DETAIL_ROWS))  # 至少保留一行，调用方传 0 不应让 UI 失去结构。
    return {
        "key": key,
        "title": title,
        "description": description,
        "columns": [{"key": column_key, "label": label} for column_key, label in columns],
        "rows": all_rows[:safe_limit],
        "total": len(all_rows),
        "truncated": len(all_rows) > safe_limit,
    }


def _score_tone(score: int) -> str:
    """把 0～100 评分映射为统一状态色语义。"""
    if score >= 85:
        return "success"
    if score >= 60:
        return "warning"
    return "danger"


def _quality_check(tone: str, title: str, message: object) -> dict[str, str]:
    """构造一条可信度核查项，统一缺省文案和类型。"""
    return {"tone": tone, "title": title, "message": _text(message)}


def _quality(
    score: object,
    summary: str,
    checks: Iterable[Mapping[str, object]] = (),
    *,
    level: str = "",
) -> dict[str, object]:
    """规范可信度评分、等级、状态色和核查项。

    分数永远钳制在 0～100；传入空等级时按分数推导客户可读等级。评分只描述识别/匹配
    质量，不应被解释为员工、供应商或生产业务绩效。
    """
    safe_score = max(0, min(100, _integer(score)))  # 防止旧 Core 或手工结果写出越界百分比。
    safe_level = level or ("可信" if safe_score >= 85 else "需复核" if safe_score >= 60 else "存疑")
    normalized_checks = []
    for item in checks:
        normalized_checks.append({
            "tone": _text(item.get("tone")) or "info",
            "title": _text(item.get("title")) or "核查项",
            "message": _text(item.get("message")),
        })
    return {
        "score": safe_score,
        "level": safe_level,
        "tone": _score_tone(safe_score),
        "summary": summary,
        "checks": normalized_checks,
    }


def _parameter(key: str, label: str, value: object) -> dict[str, str]:
    """构造可调参数展示项，不回传原始配置对象。"""
    return {"key": key, "label": label, "value": _text(value)}


def _basename(value: object) -> str:
    """只保留文件名，避免结果投影泄露服务器绝对路径。"""
    return portable_basename(_text(value))


def _ratio(part: int, total: int) -> float:
    """计算带 0 除保护且限制在 0～100 的百分比。"""
    return max(0.0, min(100.0, part / total * 100)) if total > 0 else 0.0
