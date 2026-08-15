"""Web 专用复核动作与 Core 桥接动作的组合编排。"""

from __future__ import annotations

import os
from typing import Callable


BridgeRunner = Callable[[str, int, str, dict[str, object]], object]


def _selected_values(payload: dict[str, object], keys: tuple[str, ...]):
    """只提取允许进入下游 Core 的固定字段，避免把 Web 辅助状态意外透传。

    参数 ``keys`` 是字段白名单，返回值始终是只包含白名单键的新字典；即使键不存在也
    写入 ``None``，保证下游拿到稳定结构而不是随请求体变化的残缺对象。
    """
    return {key: payload.get(key) for key in keys}


def _invoice_root(payload: dict[str, object]) -> str:
    """把一组已解析 PDF 路径收敛为发票扫描 Core 接受的共同目录。

    路径来自当前账号已解析的上传句柄，数量与边界已由上层校验；共同路径为文件时取
    其父目录，保证扫描 Core 拿到的是目录而不是单个文件。
    """
    paths = [str(path) for path in payload.get("paths", []) if path]
    if not paths:
        raise ValueError("请上传至少一个 PDF 发票文件")
    common_root = os.path.commonpath(paths)
    return os.path.dirname(common_root) if os.path.isfile(common_root) else common_root


def _execute_arrival(
    job_id: str, user_id: int, payload: dict[str, object], bridge: BridgeRunner,
) -> object:
    """执行每日到料两阶段动作，优先采用用户已经复核的批次行。

    复核阶段传入 ``rows`` 时直接使用人工结果；否则先调用 ``arrival.prepare`` 生成默认
    行，再提交 ``arrival.run``。最终仍走同一桥接协议，因此日志、进度和取消语义不变。
    """
    supplied_rows = payload.get("rows")
    if isinstance(supplied_rows, list) and supplied_rows:
        rows = supplied_rows
    else:
        prepared = bridge(
            job_id, user_id, "arrival.prepare", {"paths": payload.get("paths", [])},
        )
        rows = prepared.get("rows", []) if isinstance(prepared, dict) else []
    return bridge(job_id, user_id, "arrival.run", {
        "rows": rows,
        "top_label": payload.get("top_label", ""),
    })


def _execute_compare(
    job_id: str, user_id: int, payload: dict[str, object], bridge: BridgeRunner,
) -> object:
    """准备公共列并校验人工选择后执行两表比较。

    只把 ``file1/file2/sheet1/sheet2`` 传给准备动作，公共列优先取人工选择的键，未选择
    时回退到准备结果的第一列；比较列允许省略，但显式传入时必须为列表，防止字符串被
    Core 误当列表迭代。
    """
    base = _selected_values(payload, ("file1", "file2", "sheet1", "sheet2"))
    prepared = bridge(job_id, user_id, "compare.prepare", base)
    common = prepared.get("common", []) if isinstance(prepared, dict) else []
    key = str(payload.get("key") or (common[0] if common else ""))
    if not key:
        raise ValueError("两张表没有可用于配对的公共列")
    columns = payload.get("columns")
    if columns is not None and not isinstance(columns, list):
        raise ValueError("比较列必须是列表")
    return bridge(
        job_id, user_id, "compare.run", {**base, "key": key, "columns": columns},
    )


def _default_invoice_rows(invoices, include_normal: bool):
    """从扫描结果生成尚未人工修改时的默认发票台账行。

    ``include_normal`` 为假时只保留增值税专用发票；为真时包含普通发票。每行统一取
    种子字段或空字符串，避免把扫描结果中的内部列表直接写入台账。
    """
    return [{
        "num": item.get("num"),
        "date": item.get("date"),
        "seller": item.get("seller"),
        "item": item.get("item_seed") or "",
        "amount": item.get("amount"),
        "tax": item.get("tax"),
        "total": item.get("total"),
        "rate": item.get("rate"),
        "note": item.get("note_seed") or "",
    } for item in invoices if include_normal or item.get("special")]


def _execute_invoice(
    job_id: str, user_id: int, payload: dict[str, object], bridge: BridgeRunner,
) -> object:
    """扫描发票并将人工行或默认行提交给台账生成动作。

    先调用 ``invoice.scan`` 得到发票列表和建议月份；若用户已提交行则优先采用，否则从
    扫描结果生成默认行。月份优先级为用户选择、扫描建议、空字符串，生成动作负责最终
    校验。
    """
    scanned_envelope = bridge(
        job_id, user_id, "invoice.scan", {"root": _invoice_root(payload)},
    )
    scan = scanned_envelope.get("result", {}) if isinstance(scanned_envelope, dict) else {}
    invoices = scan.get("invoices", []) if isinstance(scan, dict) else []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = _default_invoice_rows(invoices, bool(payload.get("include_normal")))
    if not rows:
        raise ValueError("未识别到增值税专用发票")
    month = str(payload.get("month") or scan.get("suggested_month") or "")
    return bridge(
        job_id, user_id, "invoice.generate", {"scan": scan, "rows": rows, "month": month},
    )


def execute_action(
    job_id: str,
    user_id: int,
    action: str,
    payload: dict[str, object],
    bridge: BridgeRunner,
) -> object:
    """执行 Web 特殊组合动作，其余白名单动作直接透传到 Core 桥接层。

    Web 专用动作分两类：复核分析动作（``web.*.review``）只运行准备/分析阶段；组合
    动作（``web.arrival``、``web.compare``、``web.invoice``）在一次任务内编排多个 Core
    动作。其余动作必须已在调用方通过白名单校验后透传。
    """
    review_actions = {
        "web.reconcile.review": "reconcile.analyze",
        "web.pivot.review": "pivot.analyze",
        "web.supplier_batch.review": "supplier_batch.analyze",
    }
    if action in review_actions:
        return bridge(job_id, user_id, review_actions[action], payload)
    if action == "web.compare.review":
        base = _selected_values(payload, ("file1", "file2", "sheet1", "sheet2"))
        return bridge(job_id, user_id, "compare.prepare", base)
    if action == "web.invoice.review":
        return bridge(job_id, user_id, "invoice.scan", {"root": _invoice_root(payload)})
    if action == "web.arrival":
        return _execute_arrival(job_id, user_id, payload, bridge)
    if action == "web.compare":
        return _execute_compare(job_id, user_id, payload, bridge)
    if action == "web.invoice":
        return _execute_invoice(job_id, user_id, payload, bridge)
    return bridge(job_id, user_id, action, payload)

