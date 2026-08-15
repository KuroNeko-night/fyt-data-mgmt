"""任务、人工复核、模板、预览和分享服务。

本模块管理任务记录及用户可执行的 HTTP 动作；耗时业务始终交给入口层提供的
后台执行回调。所有查询都在 SQL 中绑定当前账号，文件下载还会再次校验真实路径。
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id


@dataclass(frozen=True)
class JobDependencies:
    """任务与人工复核服务依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    job_lock: Any
    job_processes: dict[str, Any]
    web_actions: dict[str, str]
    review_actions: dict[str, str]
    now_iso: Callable[[], str]
    resolve_uploads: Callable[..., list[str]]
    run_web_job: Callable[[str], None]
    job_public: Callable[[Any], dict[str, object]]
    json_list: Callable[[object], list[object]]
    json_object: Callable[[object], dict[str, object]]
    owned_result_path: Callable[..., Path]
    write_audit: Callable[[int | None, str, int | None], None]


def create_job(handler: Any, body: dict[str, object], deps: JobDependencies) -> None:
    """校验动作与上传句柄，持久化排队任务后启动后台线程。

    动作必须位于 Web 白名单，参数必须是对象，所有上传句柄在创建线程前按当前账号解析。
    数据库先写入 ``queued`` 记录，客户端随后即可轮询；守护线程启动失败之外的业务异常
    会由统一执行器写回任务状态，服务重启时未完成任务标记为中断。
    """
    user = handler.require_user()
    action = str(body.get("action") or "")
    if action not in deps.web_actions:  # 任务动作必须进入服务端白名单，不能直接调用任意 Core 命令。
        raise ApiError(HTTPStatus.BAD_REQUEST, "该功能未开放 Web 任务接口")
    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数必须是对象")
    try:
        resolved = deps.resolve_uploads(payload, int(user["id"]))  # 将不透明上传句柄解析为当前账号目录内的真实路径。
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    job_id = uuid.uuid4().hex
    title = str(body.get("title") or action)[:80]
    created = deps.now_iso()
    with deps.db_lock, deps.db() as connection:  # 先写入 queued 记录，再启动线程，客户端可立即轮询任务状态。
        connection.execute(
            "INSERT INTO web_jobs(id, user_id, action, title, status, payload, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)",
            (job_id, user["id"], action, title, json.dumps(payload, ensure_ascii=False), created, created),
        )
    threading.Thread(
        target=deps.run_web_job,
        args=(job_id, int(user["id"]), action, resolved),
        name=f"web-job-{job_id[:8]}",
        daemon=True,  # 服务退出时不阻塞进程；未完成任务会由启动迁移标记为 interrupted。
    ).start()
    handler.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)

def preflight_job(handler: Any, body: dict[str, object], deps: JobDependencies) -> None:
    """在正式创建任务前检查文件存在性、扩展名和常见误选情况。

    预检只读取解析后的参数，不创建任务、不启动子进程，也不改变上传记录。递归扫描
    所有嵌套绝对路径，返回缺失文件和可能的扩展名误选提示；提示属于辅助信息，最终
    业务校验仍由 Core 执行。
    """
    user = handler.require_user()
    action = str(body.get("action") or "")
    payload = body.get("payload") or {}
    if action not in deps.web_actions or not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数无效")
    try:
        resolved = deps.resolve_uploads(payload, int(user["id"]))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    files: list[dict[str, object]] = []
    missing: list[str] = []
    def visit(value: object) -> None:
        """递归收集解析后参数中的文件，并记录已经失效的绝对路径。

        上传句柄解析会保留普通文本参数，因此这里只把绝对路径视为候选文件；这可避免
        将工作表名称、批次号等普通字符串误报为缺失文件。
        """
        # 参数可能嵌套列表和对象，预检必须递归寻找所有绝对文件路径。
        if isinstance(value, list):
            for item in value: visit(item)
        elif isinstance(value, dict):
            for item in value.values(): visit(item)
        elif isinstance(value, str) and os.path.isabs(value):
            path = Path(value)
            if path.is_file(): files.append({"name": path.name, "size": path.stat().st_size, "suffix": path.suffix.lower()})
            else: missing.append(path.name)
    visit(resolved)
    suffixes = {str(item["suffix"]) for item in files}  # 集合只用于判断文件类型组合，不改变原文件顺序。
    warnings: list[str] = []
    if not files and any(isinstance(value, list) and value for value in payload.values()):
        warnings.append("未识别到可读取的文件")
    if any(suffix in {".xls", ".xlsx", ".xlsm"} for suffix in suffixes) and action in {"web.invoice", "web.invoice.review", "pdf.run"}:
        warnings.append("当前功能通常需要 PDF 文件，请确认上传内容")
    handler.send_json({"ok": not missing and not warnings, "files": files, "missing": missing, "warnings": warnings})

def retry_job(handler: Any, path: str, deps: JobDependencies) -> None:
    """复制失败任务的原始参数创建新任务，并保留 retry_of 追踪关系。"""
    user = handler.require_user()
    # 路由固定为 /api/jobs/{id}/retry，第三段即任务编号；更深的路径片段由上层路由拒绝。
    job_id = path.strip("/").split("/")[2]
    with deps.db_lock, deps.db() as connection:
        row = connection.execute("SELECT * FROM web_jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    if row["status"] not in {"failed", "interrupted", "cancelled"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "只有失败或中断的任务可以重试")
    try:
        payload = json.loads(row["payload"] or "{}")  # 重试始终使用最初前端参数，再重新解析当前仍有效的上传句柄。
        resolved = deps.resolve_uploads(payload, int(user["id"]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "任务资料已失效，无法重试") from exc
    new_id = uuid.uuid4().hex  # 不复用旧任务编号，旧错误、日志和版本历史继续可追溯。
    created = deps.now_iso()
    title = f"{row['title']}（重试）"[:80]
    with deps.db_lock, deps.db() as connection:
        connection.execute("INSERT INTO web_jobs(id, user_id, action, title, status, payload, retry_of, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)", (new_id, user["id"], row["action"], title, json.dumps(payload, ensure_ascii=False), job_id, created, created))
    threading.Thread(target=deps.run_web_job, args=(new_id, int(user["id"]), row["action"], resolved), name=f"web-job-retry-{new_id[:8]}", daemon=True).start()
    handler.send_json({"job_id": new_id}, HTTPStatus.ACCEPTED)

def list_jobs(handler: Any, deps: JobDependencies) -> None:
    """返回当前账号最近五十条任务，不暴露其他账号的任务记录。

    列表限制用于控制轮询响应大小；每条记录再经过 ``job_public`` 投影，把服务器路径
    转成受控下载地址并补充人工复核状态。更早任务仍保留在数据库和报表统计中。
    """
    user = handler.require_user()
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM web_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    handler.send_json({"jobs": [deps.job_public(row) for row in rows]})

def search(handler: Any, deps: JobDependencies) -> None:
    """在当前账号的任务、结果文件名和消息中执行轻量全文搜索。"""
    user = handler.require_user()
    query = str(parse_qs(urlparse(handler.path).query).get("q", [""])[0]).strip()[:100]
    if not query:
        handler.send_json({"jobs": [], "files": [], "messages": []})
        return
    like = f"%{query}%"  # 参数仍通过 SQLite 占位符传入，百分号只表达 LIKE 的包含匹配。
    with deps.db_lock, deps.db() as connection:
        jobs = connection.execute("SELECT id, title, action, status, created_at, updated_at FROM web_jobs WHERE user_id = ? AND (title LIKE ? OR action LIKE ? OR error LIKE ?) ORDER BY created_at DESC LIMIT 20", (user["id"], like, like, like)).fetchall()
        messages = connection.execute("SELECT id, title, content, created_at, read_at FROM messages WHERE recipient_user_id = ? AND (title LIKE ? OR content LIKE ?) ORDER BY created_at DESC LIMIT 20", (user["id"], like, like)).fetchall()
        files: list[dict[str, object]] = []
        for row in connection.execute("SELECT id, title, files FROM web_jobs WHERE user_id = ? AND status = 'completed' ORDER BY created_at DESC LIMIT 100", (user["id"],)).fetchall():  # 文件名存于 JSON，先限制任务数量再在 Python 中扫描。
            for index, item in enumerate(deps.json_list(row["files"])):
                if not isinstance(item, dict):
                    continue
                if query.lower() in str(item.get("name", "")).lower():
                    files.append({"name": item["name"], "size": item.get("size", 0), "url": f"/api/jobs/{row['id']}/files/{index}", "job_id": row["id"], "title": row["title"]})
    handler.send_json({"jobs": [dict(row) for row in jobs], "files": files[:20], "messages": [dict(row) for row in messages]})

def list_templates(handler: Any, deps: JobDependencies) -> None:
    """列出当前账号保存的业务参数模板。

    模板按账号隔离，参数 JSON 通过兼容解析器读取；单条历史脏数据会降级为空对象，
    不会导致整个模板页无法打开。
    """
    user = handler.require_user()
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute("SELECT id, name, action, payload, created_at, updated_at FROM web_templates WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)).fetchall()
    handler.send_json({"templates": [{"id": row["id"], "name": row["name"], "action": row["action"], "payload": deps.json_object(row["payload"]), "created_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]})

def create_template(handler: Any, body: dict[str, object], deps: JobDependencies) -> None:
    """保存当前账号可重复使用的业务动作和参数快照。

    动作仍受 Web 白名单约束，模板不能成为调用未开放 Core 动作的旁路。这里只保存前端
    参数，不提前解析上传句柄，因为临时上传可能在实际使用模板前已经失效。
    """
    user = handler.require_user()
    name = str(body.get("name") or "").strip()[:80]
    action = str(body.get("action") or "")
    payload = body.get("payload")
    if not name or action not in deps.web_actions or not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "模板名称、功能或参数无效")
    template_id = uuid.uuid4().hex
    created = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        connection.execute("INSERT INTO web_templates(id, user_id, name, action, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (template_id, user["id"], name, action, json.dumps(payload, ensure_ascii=False), created, created))
    handler.send_json({"id": template_id, "message": "任务模板已保存"}, HTTPStatus.CREATED)

def update_template(handler: Any, path: str, body: dict[str, object], deps: JobDependencies) -> None:
    """更新当前账号拥有的模板名称和参数，保持原业务动作不变。

    SQL 同时绑定模板编号和当前账号编号，所以知道他人的模板编号也不能覆盖其内容。
    业务动作不允许在编辑时改变，避免普通参数编辑悄然把模板切换到另一功能。
    """
    user = handler.require_user()
    template_id = path_id(path, "/api/templates/")
    name = str(body.get("name") or "").strip()[:80]
    payload = body.get("payload")
    if not name or not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "模板名称或参数无效")
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute("UPDATE web_templates SET name = ?, payload = ?, updated_at = ? WHERE id = ? AND user_id = ?", (name, json.dumps(payload, ensure_ascii=False), deps.now_iso(), template_id, user["id"])).rowcount
    if not changed: raise ApiError(HTTPStatus.NOT_FOUND, "模板不存在")
    handler.send_json({"message": "任务模板已更新"})

def delete_template(handler: Any, path: str, deps: JobDependencies) -> None:
    """物理删除当前账号自己的参数模板。

    模板只是可再创建的配置快照，不包含业务结果文件，因此不进入系统回收站。删除条件
    仍绑定账号编号，保证跨账号请求表现为资源不存在。
    """
    user = handler.require_user()
    template_id = path_id(path, "/api/templates/")
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute("DELETE FROM web_templates WHERE id = ? AND user_id = ?", (template_id, user["id"])).rowcount
    if not changed: raise ApiError(HTTPStatus.NOT_FOUND, "模板不存在")
    handler.send_json({"message": "任务模板已删除"})

def get_job(handler: Any, path: str, deps: JobDependencies) -> None:
    """读取当前账号的一条任务详情和标准化结果展示数据。

    所属关系在 SQL 查询中校验，不能先按任务编号查询再由前端判断。任务投影会兼容旧版
    JSON 字段，并把结果文件路径转换为同账号下载接口。
    """
    user = handler.require_user()
    job_id = path.rstrip("/").split("/")[-1]
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT * FROM web_jobs WHERE id = ? AND user_id = ?",
            (job_id, user["id"]),
        ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    handler.send_json({"job": deps.job_public(row)})

def cancel_job(handler: Any, path: str, deps: JobDependencies) -> None:
    """设置持久取消标记，并尽力终止当前任务对应的子进程。"""
    user = handler.require_user()
    # 路由固定为 /api/jobs/{id}/cancel；长度不足时编号为空，随后的账号内查询自然按不存在处理。
    parts = path.strip("/").split("/")
    job_id = parts[2] if len(parts) >= 4 else ""
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT status FROM web_jobs WHERE id = ? AND user_id = ?",
            (job_id, user["id"]),
        ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        connection.execute("UPDATE web_jobs SET cancelled = 1 WHERE id = ?", (job_id,))  # 即使进程尚未登记，后台完成前也会再次检查此标记。
    with deps.job_lock:  # 进程表由任务线程和取消请求共享，读取句柄时必须加锁。
        process = deps.job_processes.get(job_id)
    if process and process.poll() is None:
        process.terminate()  # terminate 是尽力取消；最终状态由后台线程根据 cancelled 字段统一落库。
    handler.send_json({"message": "已请求取消任务"})

def _review_payload(row: Any) -> dict[str, object]:
    """读取分析阶段保存的原始参数，并拒绝损坏或非对象历史值。"""
    try:
        payload = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError as exc:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "任务参数已损坏，无法继续复核",
        ) from exc
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数已损坏，无法继续复核")
    return payload


def _nonempty_strings(value: object, message: str) -> list[str]:
    """规范化复核多选字段，过滤空项并统一返回用户可理解的错误。"""
    if not isinstance(value, list):
        raise ApiError(HTTPStatus.BAD_REQUEST, message)
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not cleaned:
        raise ApiError(HTTPStatus.BAD_REQUEST, message)
    return cleaned


def _prepare_invoice_review(
    choices: dict[str, object], payload: dict[str, object], row: Any,
) -> None:
    """把发票保留行和月份写入最终任务参数。"""
    del row  # 所有校验均来自本次选择和原始参数，不需要分析结果。
    rows = choices.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请至少保留一张发票")
    payload["rows"] = rows
    payload["month"] = str(choices.get("month") or payload.get("month") or "")
    payload["include_normal"] = bool(choices.get("include_normal"))


def _prepare_compare_review(
    choices: dict[str, object], payload: dict[str, object], row: Any,
) -> None:
    """校验两表比较的关键列和待比较字段。"""
    del row
    key = str(choices.get("key") or "").strip()
    if not key:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请选择表格比对关键列")
    payload["key"] = key
    payload["columns"] = _nonempty_strings(
        choices.get("columns"), "请至少选择一个需要比对的字段",
    )


def _supplier_review_batches(row: Any) -> list[str]:
    """从扫描结果读取服务端认可的批次顺序，兼容历史外层 result 包装。"""
    try:
        prepared = json.loads(row["result"] or "{}")
    except json.JSONDecodeError as exc:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "批次扫描结果已损坏，请重新扫描",
        ) from exc
    plan = prepared.get("result", prepared) if isinstance(prepared, dict) else {}
    batches = plan.get("batches") if isinstance(plan, dict) else None
    expected = [
        str(item.get("batch") or "").strip()
        for item in (batches or [])
        if isinstance(item, dict) and str(item.get("batch") or "").strip()
    ]
    if not expected:
        raise ApiError(HTTPStatus.BAD_REQUEST, "批次扫描结果不完整，请重新扫描")
    return expected


def _prepare_supplier_batch_review(
    choices: dict[str, object], payload: dict[str, object], row: Any,
) -> None:
    """校验供应商选择及所有扫描批次的交付日期，拒绝遗漏和伪造批次。"""
    suppliers = _nonempty_strings(
        choices.get("suppliers"), "请至少选择一个需要制作批次表的供应商",
    )
    raw_dates = choices.get("batch_dates")
    if not isinstance(raw_dates, dict) or not raw_dates:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请填写每个批次的交付日期")

    # 键和值都转为稳定字符串；空键直接忽略，空日期留给下方覆盖校验给出统一提示。
    cleaned_dates = {
        str(batch).strip(): "" if value is None else str(value).strip()
        for batch, value in raw_dates.items()
        if str(batch).strip()
    }
    if not cleaned_dates or any(not value for value in cleaned_dates.values()):
        raise ApiError(HTTPStatus.BAD_REQUEST, "请填写每个批次的交付日期")

    expected_batches = _supplier_review_batches(row)
    expected_set = set(expected_batches)
    missing_dates = [
        batch for batch in expected_batches if not cleaned_dates.get(batch)
    ]
    if missing_dates:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "请填写以下批次的交付日期：%s" % "、".join(missing_dates),
        )
    unknown_dates = [
        batch for batch in cleaned_dates if batch not in expected_set
    ]
    if unknown_dates:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "交付日期中包含未知批次：%s" % "、".join(unknown_dates),
        )
    payload["choices"] = {
        "suppliers": suppliers,
        "batch_dates": cleaned_dates,
    }


# 人工复核准备器注册表：业务规则按动作键内聚；不在表中的动作表示 Core 已约束分析结果，
# submit_review 会原样保存用户选择对象。
_REVIEW_PREPARERS: dict[
    str, Callable[[dict[str, object], dict[str, object], Any], None]
] = {
    "web.invoice.review": _prepare_invoice_review,
    "web.compare.review": _prepare_compare_review,
    "web.supplier_batch.review": _prepare_supplier_batch_review,
}


def submit_review(handler: Any, path: str, body: dict[str, object], deps: JobDependencies) -> None:
    """校验人工复核选择，并让原任务进入服务端指定的最终动作。

    各业务选择规则由独立准备器维护；本函数只负责所属关系、状态流转、上传句柄解析和
    后台线程启动。分析动作到最终动作的映射始终来自服务端白名单，前端不能替换目标。
    """
    user = handler.require_user()
    # 路由固定为 /api/jobs/{id}/review；先解析任务编号，再校验本次提交的复核选择对象。
    parts = path.strip("/").split("/")
    job_id = parts[2] if len(parts) >= 4 else ""
    choices = body.get("choices")
    if not isinstance(choices, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "复核选择必须是对象")

    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT * FROM web_jobs WHERE id = ? AND user_id = ?",
            (job_id, user["id"]),
        ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")

    action = str(row["action"])
    if action not in deps.review_actions or row["status"] != "completed":
        raise ApiError(HTTPStatus.BAD_REQUEST, "该任务当前不可复核")
    payload = _review_payload(row)
    preparer = _REVIEW_PREPARERS.get(action)
    if preparer is None:
        # 对账单和透视表的 Core 已负责分析结果约束，Web 只保存用户选择对象。
        payload["choices"] = choices
    else:
        preparer(choices, payload, row)

    try:
        resolved = deps.resolve_uploads(payload, int(user["id"]))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    final_action = deps.review_actions[action]
    updated = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        # 复用任务编号保留审计连续性，但必须清空分析阶段快照、日志、文件和取消标志。
        connection.execute(
            "UPDATE web_jobs SET action = ?, status = 'queued', progress = 0, "
            "logs = '[]', result = NULL, error = NULL, files = '[]', "
            "cancelled = 0, updated_at = ? WHERE id = ? AND user_id = ?",
            (final_action, updated, job_id, user["id"]),
        )
    threading.Thread(
        target=deps.run_web_job,
        args=(job_id, int(user["id"]), final_action, resolved),
        name=f"web-job-review-{job_id[:8]}",
        daemon=True,
    ).start()
    handler.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)
def download_job_file(handler: Any, path: str, deps: JobDependencies) -> None:
    """下载当前账号任务的一个最新结果文件。

    接口依次校验任务所属关系、文件索引、JSON 元数据类型、真实路径边界和文件存在性。
    多层校验用于防御数据库历史脏值或被篡改路径，不能仅依赖任务查询已经按账号过滤。
    """
    user = handler.require_user()
    parts = path.strip("/").split("/")
    try:
        job_id = parts[2]
        index = int(parts[4])
    except (IndexError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "下载地址无效") from exc
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT files FROM web_jobs WHERE id = ? AND user_id = ?",
            (job_id, user["id"]),
        ).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    files = deps.json_list(row["files"])
    if index < 0 or index >= len(files) or not isinstance(files[index], dict):
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
    item = files[index]
    target = deps.owned_result_path(item.get("path"), int(user["id"]), job_id)  # JSON 中即使被写入任意绝对路径，也不能越出当前任务目录。
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件已被移动或删除")
    deps.write_audit(int(user["id"]), f"download_job:{item.get('name')}")
    handler.send_file(target, file_name=str(item["name"]))

def download_job_version_file(handler: Any, path: str, deps: JobDependencies) -> None:
    """下载当前账号任务指定历史版本中的结果文件。

    历史版本表同时绑定任务编号、账号编号和版本号；取到文件元数据后仍复用当前任务的
    结果目录边界校验。版本记录不会授予超出原任务所有者的访问权限。
    """
    user = handler.require_user()
    parts = path.strip("/").split("/")
    try:
        job_id, version, index = parts[2], int(parts[4]), int(parts[6])
    except (IndexError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "版本文件地址无效") from exc
    with deps.db_lock, deps.db() as connection:
        row = connection.execute("SELECT files FROM web_job_versions WHERE job_id = ? AND user_id = ? AND version = ?", (job_id, user["id"], version)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "结果版本不存在")
    files = deps.json_list(row["files"])
    if index < 0 or index >= len(files) or not isinstance(files[index], dict):
        raise ApiError(HTTPStatus.NOT_FOUND, "版本文件不存在")
    item = files[index]
    target = deps.owned_result_path(item.get("path"), int(user["id"]), job_id)  # 历史版本与当前结果使用相同路径隔离规则。
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "版本文件已被移动或删除")
    deps.write_audit(int(user["id"]), f"download_job_version:{item.get('name')}")
    handler.send_file(target, file_name=str(item["name"]))

def _parse_preview_path(path: str) -> tuple[str, int]:
    """从预览接口路径解析任务编号和文件下标。

    路由固定为 ``/api/jobs/{job_id}/files/{index}/preview``；任务编号必须可分割、
    文件下标必须可转整数，否则抛出 ``ApiError(400)``。返回 ``(job_id, index)``。
    """
    parts = path.strip("/").split("/")
    try:
        return parts[2], int(parts[4])
    except (IndexError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "预览地址无效") from exc


def _preview_json_file(target: Path) -> dict[str, object]:
    """把 JSON 结果文件转为有限规模的二维预览数据。

    参数 ``target`` 必须是已经通过归属校验的 JSON 结果文件。对象列表展开为表头加
    数据行，普通对象展开为键值行，其余值用单行 JSON 表示；所有分支最多保留 30 行，
    避免大型结果整体进入 HTTP 响应。文件读取、编码或 JSON 解析失败统一抛 ``ApiError``。
    """
    try:
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "JSON 文件无法读取") from exc
    if isinstance(value, list) and all(isinstance(item, dict) for item in value[:30]):
        # 对象列表转为表头加数据行，最多预览 30 条；键排序保证多次打开顺序稳定。
        keys = sorted({key for item in value[:30] for key in item})
        rows = [keys] + [[str(item.get(key, "")) for key in keys] for item in value[:30]]
        truncated = len(value) > 30
    elif isinstance(value, dict):
        rows = [[str(key), json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)]
                for key, item in list(value.items())[:30]]
        truncated = len(value) > 30
    else:
        rows = [[json.dumps(value, ensure_ascii=False)]]
        truncated = False
    return {"sheet": "", "sheets": [], "rows": rows, "truncated": truncated}


def preview_job_file(handler: Any, path: str, deps: JobDependencies) -> None:
    """为当前账号的结果文件生成有限行列的结构化预览。

    JSON 对象和对象列表直接转为二维数据；Excel 类文件交给 Core 预览器读取；PDF 由
    浏览器原生打开。所有分支都先执行任务所属与真实路径校验，并限制预览规模，避免把
    大型结果整体载入 HTTP 请求线程。
    """
    user = handler.require_user()
    job_id, index = _parse_preview_path(path)
    with deps.db_lock, deps.db() as connection:
        row = connection.execute("SELECT files FROM web_jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    files = deps.json_list(row["files"])
    if index < 0 or index >= len(files) or not isinstance(files[index], dict):
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
    target = deps.owned_result_path(files[index].get("path"), int(user["id"]), job_id)
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件已被移动或删除")
    if target.suffix.lower() == ".pdf":  # PDF 由浏览器原生查看，表格预览器不重复解析。
        raise ApiError(HTTPStatus.BAD_REQUEST, "PDF 文件请直接打开查看")
    if target.suffix.lower() == ".json":
        payload = _preview_json_file(target)
        payload.update(name=target.name)
        handler.send_json(payload)
        return
    from core import preview_core
    preview = preview_core.read_preview(str(target), max_rows=30, max_cols=40)  # 限制二维范围，避免大工作簿预览阻塞请求线程。
    if preview.error:
        raise ApiError(HTTPStatus.BAD_REQUEST, preview.error)
    handler.send_json({
        "name": target.name, "sheet": preview.sheet, "sheets": preview.sheets,
        "rows": preview.rows, "truncated": preview.truncated,
    })

def assign_job(handler: Any, path: str, body: dict[str, object], deps: JobDependencies) -> None:
    """管理员把任务指派给正常账号，并在同一事务中发送定向提醒。

    空接收者表示取消指派；非空编号必须对应正常使用账号。任务指派与消息写入一起提交，
    避免任务已显示负责人但通知未生成的半完成状态；取消指派不产生无意义消息。
    """
    user = handler.require_user(admin=True)
    job_id = str(path.strip("/").split("/")[2])
    raw = body.get("assignee_id")
    assignee_id = int(raw) if raw not in (None, "") else None  # 空值表示取消指派，不使用 0 作为特殊账号编号。
    with deps.db_lock, deps.db() as connection:
        job = connection.execute(
            "SELECT title FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        if assignee_id is not None:  # 指派对象必须仍处于正常状态，停用账号不能接收任务。
            target = connection.execute(
                "SELECT id, status FROM users WHERE id = ?", (assignee_id,)).fetchone()
            if target is None or target["status"] != "approved":
                raise ApiError(HTTPStatus.BAD_REQUEST, "只能指派给正常使用的账号")
        connection.execute(
            "UPDATE web_jobs SET assignee_id = ? WHERE id = ?", (assignee_id, job_id))
        if assignee_id is not None:
            connection.execute(
                "INSERT INTO messages(recipient_user_id, title, content, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (assignee_id, "有任务需要你确认",
                 f"任务「{job['title']}」已指派给你，请到任务中心查看并处理。",
                 int(user["id"]), deps.now_iso()),
            )
    handler.send_json({"message": "已指派" if assignee_id is not None else "已取消指派"})

def create_share(handler: Any, body: dict[str, object], deps: JobDependencies) -> None:
    """为当前账号任务的指定结果文件生成一至三十天限时分享链接。

    任务所属关系和文件索引在创建令牌前校验，匿名地址使用高熵随机令牌而不是可预测的
    任务编号。分享只保存文件索引，下载时会重新读取任务结果并执行原所有者目录边界
    校验，文件被移动或删除后链接自然失效。
    """
    user = handler.require_user()
    job_id = str(body.get("job_id") or "")
    try:
        file_index = int(body.get("file_index"))
    except (TypeError, ValueError):
        raise ApiError(HTTPStatus.BAD_REQUEST, "文件序号无效") from None
    try:
        days = max(1, min(30, int(body.get("expires_in_days", 7))))  # 分享有效期强制限制为 1 至 30 天。
    except (TypeError, ValueError):
        days = 7
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT files FROM web_jobs WHERE id = ? AND user_id = ?",
            (job_id, int(user["id"])),
        ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        files = deps.json_list(row["files"])
        if file_index < 0 or file_index >= len(files) or not isinstance(files[file_index], dict):
            raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
        token = secrets.token_urlsafe(24)  # 匿名 URL 使用高熵令牌，不能由任务编号推测。
        created = deps.now_iso()
        expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
        connection.execute(
            "INSERT INTO share_tokens(token, job_id, file_index, created_by, created_at, expires_at, revoked) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (token, job_id, file_index, int(user["id"]), created, expires),
        )
    item = files[file_index]
    handler.send_json({
        "token": token, "url": f"/api/shares/{token}",
        "name": str(item.get("name", "")), "expires_at": expires,
    })

def download_shared_file(handler: Any, path: str, deps: JobDependencies) -> None:
    """匿名下载分享文件，并校验令牌存在、未撤销、未过期和路径归属。

    分享链接不要求登录，因此所有安全性依赖高熵令牌和服务端复查。任务、文件索引或
    实体文件任一缺失都会拒绝下载；最终路径仍必须位于原任务账号的受控输出目录。
    """
    token = str(path.strip("/").split("/")[-1])
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT * FROM share_tokens WHERE token = ?", (token,)).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "分享不存在")
        if row["revoked"]:
            raise ApiError(HTTPStatus.GONE, "分享已撤销")
        if row["expires_at"] and str(row["expires_at"]) < deps.now_iso():  # ISO 时间统一为带时区格式，可安全按字符串比较先后。
            raise ApiError(HTTPStatus.GONE, "分享已过期")
        job = connection.execute(
            "SELECT user_id, files FROM web_jobs WHERE id = ?", (row["job_id"],)).fetchone()
    if job is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
    files = deps.json_list(job["files"])
    file_index = int(row["file_index"])
    if file_index < 0 or file_index >= len(files) or not isinstance(files[file_index], dict):
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
    item = files[file_index]
    target = deps.owned_result_path(item.get("path"), int(job["user_id"]), str(row["job_id"]))  # 匿名分享仍执行原所有者目录校验。
    if not target.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "结果文件已被移动或删除")
    handler.send_file(target)

def revoke_share(handler: Any, path: str, deps: JobDependencies) -> None:
    """撤销自己创建的分享链接。"""
    user = handler.require_user()
    token = str(path.strip("/").split("/")[-1])
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT created_by FROM share_tokens WHERE token = ?", (token,)).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "分享不存在")
        if int(row["created_by"]) != int(user["id"]):
            raise ApiError(HTTPStatus.FORBIDDEN, "只能撤销自己创建的分享")
        connection.execute("UPDATE share_tokens SET revoked = 1 WHERE token = ?", (token,))
    handler.send_json({"message": "分享已撤销"})
