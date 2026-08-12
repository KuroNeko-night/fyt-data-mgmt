# -*- coding: utf-8 -*-
"""
桌面端后台任务历史
==================
使用标准库 SQLite 记录业务任务的开始、结束、取消、异常中断、耗时、输出目录和少量
元数据。每次公开操作独立建立短连接，适配桌面主线程、工作线程和 Tauri 桥接回调，
核心层不依赖任何界面。

任务历史是审计与体验辅助能力：数据库打开、迁移或写入失败时，公开写操作返回空值或
假值，不反向改变业务任务结果。连接上下文负责建表、补充旧数据库缺失字段、提交和
回滚；程序启动时可把遗留 running 任务统一标为 interrupted。

本模块记录的是本机桌面任务历史。Web 服务拥有独立持久化任务和用户隔离机制，不应
把本地 SQLite 路径直接暴露给前端或不同用户共享。
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
    """返回带本地时区偏移的秒级 ISO 时间文本。"""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


@contextlib.contextmanager
def _connect(db_path=None):
    """打开任务历史数据库，确保 schema 就绪，并管理事务生命周期。

    显式路径供测试隔离，默认路径来自 ``core.paths``。每次连接都会幂等建表和索引，
    并检查旧数据库是否缺少 ``request_id`` 列；上下文正常退出时提交，异常时回滚后
    重新抛出，最终始终关闭连接。八秒超时给并发短写入留出等待空间。
    """
    path = db_path or paths.task_history_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    conn = sqlite3.connect(path, timeout=8.0)
    try:
        # Row 允许按列名读取，降低 schema 列顺序变化导致的维护风险。
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(task_history)")}
        if "request_id" not in columns:
            # 兼容早期数据库：ALTER 只在确实缺列时执行，避免每次连接报重复列错误。
            conn.execute("ALTER TABLE task_history ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_request "
                     "ON task_history(request_id, status)")
        yield conn
        conn.commit()
    except Exception:
        # 任何调用内 SQL 失败都回滚本次连接上的全部改动，避免留下半更新任务。
        conn.rollback()
        raise
    finally:
        conn.close()


def start_task(feature, title, meta=None, db_path=None):
    """创建一条运行中任务并返回 16 位随机任务编号。

    元数据使用 JSON 保存，非标准对象转字符串；若含 ``request_id``，同时复制到独立
    索引列供 Tauri 精确取消。记录失败返回空串，调用方仍应继续执行实际业务。
    """
    task_id = uuid.uuid4().hex[:16]  # 本地历史标识，无需承担认证或安全令牌用途。
    now_ts = time.time()  # 浮点时间戳用于计算耗时和排序，展示时间另存 ISO 文本。
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
        # 历史记录故障不能阻断业务入口，空 ID 会让 finish_task 安全地跳过。
        return ""


def finish_task(task_id, status="ok", message="", output_dir="", db_path=None):
    """结束仍处于 running 的任务并写入状态、耗时和结果摘要。

    状态只允许 ok、failed、cancelled、interrupted，未知值按 failed 处理。仅更新仍为
    running 的同 ID 记录，保证重复完成、取消后完成或旧回调不会覆盖最终状态。消息
    最多保存 2000 字符，防止完整异常堆栈无限放大数据库。
    """
    if not task_id:
        return False
    status = status if status in ("ok", "failed", "cancelled", "interrupted") else "failed"
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT started_ts FROM task_history WHERE id=? AND status='running'", (task_id,)).fetchone()
            if row is None:
                # 任务不存在或已被其他路径结束时视为无操作，不修改历史终态。
                return False
            # 系统时间回拨时用 max(0) 防止展示负耗时。
            duration_ms = max(0, int((time.time() - float(row["started_ts"])) * 1000))
            conn.execute(
                "UPDATE task_history SET status=?,finished_at=?,duration_ms=?,"
                "message=?,output_dir=? WHERE id=? AND status='running'",
                (status, _now_text(), duration_ms, str(message or "")[:2000],
                 str(output_dir or ""), task_id))
        return True
    except Exception:
        # 与 start_task 一致，历史写入失败只通过返回值告知调用方。
        return False


def mark_interrupted(db_path=None):
    """把数据库中遗留的全部 running 任务标记为异常中断。

    通常在应用启动时调用。耗时按当前时间与原开始时间计算；原消息为空时补充统一说明，
    已有诊断信息则保留。返回受影响行数，数据库不可用时返回零。
    """
    try:
        now_ts = time.time()
        with _connect(db_path) as conn:
            cur = conn.execute(
                "UPDATE task_history SET status='interrupted',finished_at=?,"
                # SQLite 内完成批量耗时计算，避免先查询再逐行更新造成竞争窗口。
                "duration_ms=MAX(0,CAST((?-started_ts)*1000 AS INTEGER)),"
                "message=CASE WHEN message='' THEN '程序退出前任务未正常结束' ELSE message END "
                "WHERE status='running'", (_now_text(), now_ts))
            return cur.rowcount
    except Exception:
        return 0


def list_recent(limit=100, db_path=None):
    """返回最近任务的展示字段字典列表，按开始时间倒序。

    数量强制限制在 1 到 1000，避免界面误传极大值造成长查询；内部 meta 和 request_id
    不返回给普通历史列表，减少实现细节暴露。查询失败返回空列表。
    """
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
    """汇总总任务数和各已知状态数量，数据库异常时返回全零结构。"""
    result = {"total": 0, "running": 0, "ok": 0, "failed": 0,
              "cancelled": 0, "interrupted": 0}
    try:
        with _connect(db_path) as conn:
            for row in conn.execute(
                    "SELECT status,COUNT(*) AS n FROM task_history GROUP BY status"):
                # 若历史数据库未来出现新状态，也会动态加入结果并计入 total。
                result[row["status"]] = int(row["n"])
                result["total"] += int(row["n"])
    except Exception:
        pass
    return result


def clear_finished(db_path=None):
    """删除所有非 running 历史并返回数量。

    本函数执行不可逆删除且不负责交互确认；桌面或 Web 管理入口必须在调用前明确获得
    用户确认。运行中任务始终保留，避免清理操作破坏当前状态跟踪。
    """
    try:
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM task_history WHERE status!='running'")
            return cur.rowcount
    except Exception:
        return 0


def cancel_request(request_id, db_path=None):
    """按 Tauri 请求编号批量结束仍在运行的关联任务。

    一个请求通常对应一条任务，但 SQL 保留批量语义。只更新 running 记录，写入统一
    取消消息并清空输出目录，避免取消任务展示尚未完成的产物路径。返回更新行数。
    """
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
