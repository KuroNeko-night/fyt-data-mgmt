# -*- coding: utf-8 -*-
"""
任务历史 —— 统一记录后台业务任务的运行状态
==========================================
使用标准库 SQLite，每次操作独立连接，适配 UI 主线程与 Worker 回调。
core 层不依赖 Qt；记录失败不能反向影响业务任务。
"""
import datetime
import contextlib
import json
import os
import sqlite3
import time
import uuid

from . import paths


_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_history (
    id TEXT PRIMARY KEY,
    feature TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    started_ts REAL NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,
    message TEXT NOT NULL DEFAULT '',
    output_dir TEXT NOT NULL DEFAULT '',
    meta_json TEXT NOT NULL DEFAULT '{}',
    request_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_task_history_started
ON task_history(started_ts DESC);
CREATE INDEX IF NOT EXISTS idx_task_history_status
ON task_history(status);
"""


def _now_text():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


@contextlib.contextmanager
def _connect(db_path=None):
    path = db_path or paths.task_history_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    conn = sqlite3.connect(path, timeout=8.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(task_history)")}
        if "request_id" not in columns:
            conn.execute("ALTER TABLE task_history ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_request "
                     "ON task_history(request_id, status)")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def start_task(feature, title, meta=None, db_path=None):
    """创建 running 任务并返回任务编号。记录失败时返回空串。"""
    task_id = uuid.uuid4().hex[:16]
    now_ts = time.time()
    request_id = str((meta or {}).get("request_id") or "")
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO task_history "
                "(id,feature,title,status,started_at,started_ts,meta_json,request_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (task_id, feature or "unknown", title or "后台任务", "running",
                  _now_text(), now_ts,
                 json.dumps(meta or {}, ensure_ascii=False, default=str), request_id))
        return task_id
    except Exception:
        return ""


def finish_task(task_id, status="ok", message="", output_dir="", db_path=None):
    """完成任务并写入耗时。status 支持 ok/failed/cancelled/interrupted。"""
    if not task_id:
        return False
    status = status if status in ("ok", "failed", "cancelled", "interrupted") else "failed"
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT started_ts FROM task_history WHERE id=? AND status='running'", (task_id,)).fetchone()
            if row is None:
                return False
            duration_ms = max(0, int((time.time() - float(row["started_ts"])) * 1000))
            conn.execute(
                "UPDATE task_history SET status=?,finished_at=?,duration_ms=?,"
                "message=?,output_dir=? WHERE id=? AND status='running'",
                (status, _now_text(), duration_ms, str(message or "")[:2000],
                 str(output_dir or ""), task_id))
        return True
    except Exception:
        return False


def mark_interrupted(db_path=None):
    """把上次异常退出遗留的 running 任务标为 interrupted。"""
    try:
        now_ts = time.time()
        with _connect(db_path) as conn:
            cur = conn.execute(
                "UPDATE task_history SET status='interrupted',finished_at=?,"
                "duration_ms=MAX(0,CAST((?-started_ts)*1000 AS INTEGER)),"
                "message=CASE WHEN message='' THEN '程序退出前任务未正常结束' ELSE message END "
                "WHERE status='running'", (_now_text(), now_ts))
            return cur.rowcount
    except Exception:
        return 0


def list_recent(limit=100, db_path=None):
    """按开始时间倒序返回最近任务字典。"""
    limit = max(1, min(1000, int(limit)))
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                "SELECT id,feature,title,status,started_at,finished_at,duration_ms,"
                "message,output_dir FROM task_history ORDER BY started_ts DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def summary(db_path=None):
    """返回总数与各状态数量。"""
    result = {"total": 0, "running": 0, "ok": 0, "failed": 0,
              "cancelled": 0, "interrupted": 0}
    try:
        with _connect(db_path) as conn:
            for row in conn.execute(
                    "SELECT status,COUNT(*) AS n FROM task_history GROUP BY status"):
                result[row["status"]] = int(row["n"])
                result["total"] += int(row["n"])
    except Exception:
        pass
    return result


def clear_finished(db_path=None):
    """清除非运行中历史，返回删除数量。调用方必须先向用户确认。"""
    try:
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM task_history WHERE status!='running'")
            return cur.rowcount
    except Exception:
        return 0


def cancel_request(request_id, db_path=None):
    """按 Tauri 请求编号标记对应运行中任务为已取消。"""
    if not request_id:
        return 0
    try:
        now_ts = time.time()
        with _connect(db_path) as conn:
            cur = conn.execute(
                "UPDATE task_history SET status='cancelled',finished_at=?,"
                "duration_ms=MAX(0,CAST((?-started_ts)*1000 AS INTEGER)),"
                "message='用户已取消任务',output_dir='' "
                "WHERE request_id=? AND status='running'",
                (_now_text(), now_ts, request_id))
            return cur.rowcount
    except Exception:
        return 0
