# -*- coding: utf-8 -*-
"""双端结构化业务结果投影入口。

公共规范化、日清类、采购运营类和财务类投影已经分层维护。本门面保留 present、
arrival_batches、canonical_kind 和 unwrap_result 等现有公开入口；未注册业务仍返回
None，由前端回退到正式输出文件摘要。
"""

from __future__ import annotations

from collections.abc import Callable

from .business_result_common import (
    MAX_DETAIL_ROWS,
    canonical_kind,
    unwrap_result,
)
from .business_result_daily import (
    _present_arrival,
    _present_attendance,
    _present_attendance_archive,
    arrival_batches,
)
from .business_result_operations import (
    _present_delivery,
    _present_pivot,
    _present_purchase,
    _present_purchase_diff,
    _present_purchase_plan,
    _present_reconcile,
    _present_supplier_batch,
)
from .business_result_finance import (
    _present_compare,
    _present_invoice,
    _present_invoice_match,
    _present_reconcile_statement,
)


_PRESENTERS: dict[str, Callable[[object, int], dict[str, object] | None]] = {
    "arrival": _present_arrival,
    "attendance": _present_attendance,
    "attendance_archive": _present_attendance_archive,
    "reconcile": _present_reconcile,
    "pivot": _present_pivot,
    "purchase": _present_purchase,
    "delivery": _present_delivery,
    "supplier_batch": _present_supplier_batch,
    "purchase_plan": _present_purchase_plan,
    "purchase_diff": _present_purchase_diff,
    "reconcile_statement": _present_reconcile_statement,
    "invoice": _present_invoice,
    "invoice_match": _present_invoice_match,
    "compare": _present_compare,
}


def present(
    kind: object,
    value: object,
    limit: int = MAX_DETAIL_ROWS,
) -> dict[str, object] | None:
    """返回统一结果展示结构；未注册或无法识别的模块返回 None。

    投影是业务成功后的辅助展示层。调用方应把 None 解释为“仍可查看和下载输出文件”，
    不能把投影缺失升级为任务失败；明细上限至少保留一行。
    """
    presenter = _PRESENTERS.get(canonical_kind(kind))
    if presenter is None:
        return None
    return presenter(value, max(1, int(limit or MAX_DETAIL_ROWS)))


__all__ = [
    "MAX_DETAIL_ROWS",
    "arrival_batches",
    "canonical_kind",
    "present",
    "unwrap_result",
]
