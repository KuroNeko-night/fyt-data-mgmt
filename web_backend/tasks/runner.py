"""Web 后台任务的状态流转、版本持久化、清理与完成通知。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RunnerDependencies:
    """后台状态机使用的数据库、动作执行、结果处理和辅助维护能力。"""

    db_lock: Any
    db: Callable[[], Any]
    now_iso: Callable[[], str]
    update_job: Callable[..., None]
    execute_action: Callable[[str, int, str, dict[str, object]], object]
    collect_result_files: Callable[[object], list[dict[str, object]]]
    public_result: Callable[[object], object]
    enforce_output_retention: Callable[[], int]
    notify_webhook: Callable[[str, str], None]
    review_actions: dict[str, str]


def _cancelled(job_id: str, deps: RunnerDependencies) -> bool:
    """读取任务取消标志；查询与调用方其他事务分离，避免长时间持锁。"""
    with deps.db_lock, deps.db() as connection:
        row = connection.execute(
            "SELECT cancelled FROM web_jobs WHERE id = ?", (job_id,),
        ).fetchone()
    return bool(row and row["cancelled"])


def _persist_completed_version(
    job_id: str,
    user_id: int,
    public_value: object,
    files: list[dict[str, object]],
    deps: RunnerDependencies,
) -> None:
    """在同一事务中计算下一版本号并写入不可变任务版本。"""
    result_json = json.dumps(public_value, ensure_ascii=False)
    files_json = json.dumps(files, ensure_ascii=False)
    # 版本号与插入在同一事务和 DB_LOCK 内计算，并发完成任务也不会产生重复版本。
    with deps.db_lock, deps.db() as connection:
        latest = connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM web_job_versions WHERE job_id = ?",
            (job_id,),
        ).fetchone()["version"]
        connection.execute(
            "INSERT INTO web_job_versions"
            "(job_id, user_id, version, result, files, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'completed', ?)",
            (job_id, user_id, int(latest) + 1, result_json, files_json, deps.now_iso()),
        )


def _job_summary(job_id: str, deps: RunnerDependencies):
    """读取通知所需的最小任务字段，避免把完整结果再次载入内存。"""
    with deps.db_lock, deps.db() as connection:
        return connection.execute(
            "SELECT title, action FROM web_jobs WHERE id = ?", (job_id,),
        ).fetchone()


def _notify_success(job_id: str, deps: RunnerDependencies) -> None:
    """按是否等待人工复核发送任务完成通知。"""
    row = _job_summary(job_id, deps)
    if row is None:
        return
    state = "待人工复核" if row["action"] in deps.review_actions else "已完成"
    deps.notify_webhook(
        "任务%s：%s" % (state, row["title"]),
        "动作：%s" % row["action"],
    )


def _record_failure(job_id: str, error: Exception, deps: RunnerDependencies) -> None:
    """区分主动取消与业务失败，持久化状态后发送简短通知。"""
    cancelled = _cancelled(job_id, deps)
    deps.update_job(
        job_id,
        status="cancelled" if cancelled else "failed",
        error="任务已取消" if cancelled else str(error),
    )
    row = _job_summary(job_id, deps)
    if row is not None:
        state = "已取消" if cancelled else "处理失败"
        deps.notify_webhook("任务%s：%s" % (state, row["title"]), str(error)[:200])


def run_web_job(
    job_id: str,
    user_id: int,
    action: str,
    payload: dict[str, object],
    deps: RunnerDependencies,
) -> None:
    """执行任务并按“运行、版本落库、完成或失败”驱动持久化状态机。"""
    deps.update_job(job_id, status="running", progress=1)
    try:
        result = deps.execute_action(job_id, user_id, action, payload)
        if _cancelled(job_id, deps):
            deps.update_job(job_id, status="cancelled", error="任务已取消")
            return
        files = deps.collect_result_files(result)
        public_value = deps.public_result(result)
        # 版本必须先落库再更新主任务状态；即使后续保留策略失败，本次结果也已持久化可追踪。
        _persist_completed_version(job_id, user_id, public_value, files, deps)
        deps.update_job(
            job_id,
            status="completed",
            progress=100,
            result=json.dumps(public_value, ensure_ascii=False),
            files=json.dumps(files, ensure_ascii=False),
        )
        try:
            deps.enforce_output_retention()
        except Exception as maintenance_error:
            # 保留策略属于任务完成后的辅助维护，失败不能撤销已经成功持久化的业务结果。
            print(f"[维护] 输出保留检查暂未完成：{maintenance_error}")
        _notify_success(job_id, deps)
    except Exception as error:  # 具体 Core 异常由状态字段返回客户端，不在线程中继续抛出。
        _record_failure(job_id, error, deps)

