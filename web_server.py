"""峰运通数据管理系统局域网 Web 服务端。

运行于 Windows 10/11 + Python 3.13。使用标准库提供静态文件托管、SQLite
账号管理、注册审核与会话认证，避免给桌面端增加 Web 运行时依赖。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web-app"
STATIC_ROOT = WEB_ROOT / "dist"
DATA_ROOT = Path(os.environ.get("FYT_WEB_DATA", ROOT / "web-data"))
DB_PATH = DATA_ROOT / "accounts.sqlite3"
HOST = os.environ.get("FYT_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("FYT_WEB_PORT", "8787"))
SESSION_DAYS = 7
PBKDF2_ROUNDS = 240_000
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DB_LOCK = threading.RLock()
JOB_LOCK = threading.RLock()
JOB_PROCESSES: dict[str, subprocess.Popen[str]] = {}

WEB_ACTIONS = {
    "attendance.run", "reconcile.run", "pivot.run", "purchase.run",
    "delivery.run", "library.import", "rename.apply", "pdf.run",
    "excel.run", "currency.convert", "text.transform",
    "web.arrival", "web.invoice", "web.compare",
}

# 需要人工确认的业务先运行只读分析，确认后把同一个任务切回最终动作。
REVIEW_ACTIONS = {
    "web.reconcile.review": "reconcile.run",
    "web.pivot.review": "pivot.run",
    "web.invoice.review": "web.invoice",
    "web.compare.review": "web.compare",
}
WEB_ACTIONS.update(REVIEW_ACTIONS)


def feature_key_for_action(action: object) -> str:
    """从普通或 Web 复核动作中提取看板使用的业务功能键。"""
    parts = str(action or "").split(".")
    if parts[0] == "web" and len(parts) > 1:
        return parts[1]
    return parts[0]


def is_review_pending(row: sqlite3.Row) -> bool:
    """判断任务是否已完成分析、正在等待人工确认。"""
    return row["action"] in REVIEW_ACTIONS and row["status"] == "completed"

FEATURES = [
    {"key": "attendance", "title": "考勤填报", "group": "人事", "description": "自动整理打卡数据并生成工时填报表"},
    {"key": "reconcile", "title": "工时对账", "group": "人事", "description": "多方工时核对与异常汇总"},
    {"key": "arrival", "title": "到料明细", "group": "业务", "description": "根据送货计划追踪到料进度"},
    {"key": "pivot", "title": "销售透视", "group": "业务", "description": "清洗、汇总并输出可信度报告"},
    {"key": "purchase", "title": "采购对账", "group": "业务", "description": "供应商采购数量逐行比对"},
    {"key": "delivery", "title": "送货计划", "group": "业务", "description": "从物料清单生成送货计划"},
    {"key": "library", "title": "数据仓库", "group": "数据", "description": "集中归档、检索与复用业务表格"},
    {"key": "invoice", "title": "发票统计", "group": "财务", "description": "扫描 PDF 发票并按月汇总"},
    {"key": "rename", "title": "批量重命名", "group": "工具", "description": "规则化改名并下载处理后的文件"},
    {"key": "text", "title": "文本工具", "group": "工具", "description": "文本去重、排序、清理与内容提取"},
    {"key": "pdf", "title": "PDF 工具", "group": "工具", "description": "PDF 合并、拆分、提取与删页"},
    {"key": "excel", "title": "Excel 工具", "group": "工具", "description": "表格合并、拆分、转换与纵向汇总"},
    {"key": "compare", "title": "表格比对", "group": "工具", "description": "按关键列定位新增、删除与差异"},
    {"key": "currency", "title": "金额大写", "group": "财务", "description": "人民币金额转换为中文大写"},
]


class ManagedConnection(sqlite3.Connection):
    """让 ``with db()`` 在提交后同时释放 Windows 文件句柄。"""

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


def db() -> sqlite3.Connection:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False, factory=ManagedConnection)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with DB_LOCK, db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                approved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uploads (
                handle TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                group_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                logs TEXT NOT NULL DEFAULT '[]',
                result TEXT,
                error TEXT,
                files TEXT NOT NULL DEFAULT '[]',
                cancelled INTEGER NOT NULL DEFAULT 0,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        # 老版本数据库没有任务 payload，使用幂等迁移以保留已有任务记录。
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(web_jobs)").fetchall()}
        if "payload" not in columns:
            connection.execute("ALTER TABLE web_jobs ADD COLUMN payload TEXT NOT NULL DEFAULT '{}'")
        admin = connection.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if admin is None:
            salt, digest = hash_password(os.environ.get("FYT_ADMIN_PASSWORD", "admin123456"))
            connection.execute(
                "INSERT INTO users(username, display_name, salt, password_hash, role, status, created_at, approved_at) VALUES (?, ?, ?, ?, 'admin', 'approved', ?, ?)",
                ("admin", "系统管理员", salt, digest, now_iso(), now_iso()),
            )
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        connection.execute(
            "UPDATE web_jobs SET status = 'interrupted', error = ? "
            "WHERE status IN ('queued', 'running')",
            ("服务端重启，任务已中断",),
        )


def user_public(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"], "username": row["username"], "display_name": row["display_name"],
        "role": row["role"], "status": row["status"], "created_at": row["created_at"],
        "approved_at": row["approved_at"],
    }


def safe_name(value: str) -> str:
    """把浏览器文件名收敛为服务端可安全保存的单层名称。"""
    name = Path(value.replace("\\", "/")).name.strip().strip(".")
    name = "".join(char for char in name if char not in '<>:"/\\|?*' and ord(char) >= 32)
    return name[:180] or "未命名文件"


def update_job(job_id: str, **values: object) -> None:
    """原子更新 Web 任务状态。"""
    if not values:
        return
    values["updated_at"] = now_iso()
    columns = ", ".join(f"{key} = ?" for key in values)
    with DB_LOCK, db() as connection:
        connection.execute(
            f"UPDATE web_jobs SET {columns} WHERE id = ?",
            (*values.values(), job_id),
        )


def append_job_log(job_id: str, message: str) -> None:
    """追加任务日志并限制历史长度，避免数据库无限增长。"""
    with DB_LOCK, db() as connection:
        row = connection.execute("SELECT logs FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
        logs = json.loads(row["logs"] or "[]") if row else []
        logs.append(str(message))
        connection.execute(
            "UPDATE web_jobs SET logs = ?, updated_at = ? WHERE id = ?",
            (json.dumps(logs[-500:], ensure_ascii=False), now_iso(), job_id),
        )


def resolve_uploads(value: object, user_id: int) -> object:
    """递归把用户上传句柄解析为所属文件路径，拒绝跨用户引用。"""
    if isinstance(value, dict):
        return {key: resolve_uploads(item, user_id) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_uploads(item, user_id) for item in value]
    if not isinstance(value, str):
        return value
    if value.startswith("upload:"):
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT path FROM uploads WHERE handle = ? AND user_id = ?",
                (value, user_id),
            ).fetchone()
        if row is None or not os.path.isfile(row["path"]):
            raise ValueError("上传文件不存在或不属于当前账号")
        return row["path"]
    if value.startswith("upload-group:"):
        group_id = value.split(":", 1)[1]
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT path FROM uploads WHERE group_id = ? AND user_id = ? LIMIT 1",
                (group_id, user_id),
            ).fetchone()
        if row is None:
            raise ValueError("上传批次不存在或不属于当前账号")
        return str(Path(row["path"]).parent)
    return value


def run_bridge(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> object:
    """在独立 Python 进程执行桥接动作，并转发日志与进度。"""
    env = os.environ.copy()
    output_root = DATA_ROOT / "users" / str(user_id) / "jobs" / job_id / "outputs"
    cache_path = DATA_ROOT / "users" / str(user_id) / "cache" / "增量缓存.json"
    env.update({
        "PYTHONIOENCODING": "utf-8", "FYT_BRIDGE_EVENTS": "1",
        "FYT_REQUEST_ID": job_id, "FYT_WEB_OUTPUT_ROOT": str(output_root),
        "FYT_INCREMENTAL_CACHE_PATH": str(cache_path),
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "core.tauri_bridge"],
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    with JOB_LOCK:
        JOB_PROCESSES[job_id] = process
    request = json.dumps({"action": action, "payload": payload}, ensure_ascii=False)
    assert process.stdin is not None
    process.stdin.write(request)
    process.stdin.close()
    stderr_lines: list[str] = []

    def read_events() -> None:
        assert process.stderr is not None
        for raw in process.stderr:
            line = raw.rstrip()
            if line.startswith("__FYT_EVENT__"):
                try:
                    event = json.loads(line[len("__FYT_EVENT__"):])
                    if event.get("kind") == "log":
                        append_job_log(job_id, str(event.get("value", "")))
                    elif event.get("kind") == "progress":
                        update_job(job_id, progress=max(0, min(99, int(event.get("value", 0)))))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
            elif line:
                stderr_lines.append(line)

    reader = threading.Thread(target=read_events, daemon=True)
    reader.start()
    assert process.stdout is not None
    raw_output = process.stdout.read()
    return_code = process.wait()
    reader.join(timeout=2)
    process.stdout.close()
    process.stderr.close()
    with JOB_LOCK:
        JOB_PROCESSES.pop(job_id, None)
    if return_code != 0:
        detail = stderr_lines[-1] if stderr_lines else "业务核心进程执行失败"
        raise RuntimeError(detail)
    response = json.loads(raw_output or "{}")
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "业务核心返回失败"))
    return response.get("data")


def execute_action(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> object:
    """执行直接桥接动作或 Web 端需要的多阶段组合动作。"""
    if action == "web.reconcile.review":
        return run_bridge(job_id, user_id, "reconcile.analyze", payload)
    if action == "web.pivot.review":
        return run_bridge(job_id, user_id, "pivot.analyze", payload)
    if action == "web.compare.review":
        base = {key: payload.get(key) for key in ("file1", "file2", "sheet1", "sheet2")}
        return run_bridge(job_id, user_id, "compare.prepare", base)
    if action == "web.invoice.review":
        paths = [str(path) for path in payload.get("paths", []) if path]
        if not paths:
            raise ValueError("请上传至少一个 PDF 发票文件")
        root = os.path.commonpath(paths)
        if os.path.isfile(root):
            root = os.path.dirname(root)
        return run_bridge(job_id, user_id, "invoice.scan", {"root": root})
    if action == "web.arrival":
        prepared = run_bridge(job_id, user_id, "arrival.prepare", {"paths": payload.get("paths", [])})
        return run_bridge(job_id, user_id, "arrival.run", {
            "rows": prepared.get("rows", []) if isinstance(prepared, dict) else [],
            "top_label": payload.get("top_label", ""),
        })
    if action == "web.compare":
        base = {key: payload.get(key) for key in ("file1", "file2", "sheet1", "sheet2")}
        prepared = run_bridge(job_id, user_id, "compare.prepare", base)
        common = prepared.get("common", []) if isinstance(prepared, dict) else []
        key = str(payload.get("key") or (common[0] if common else ""))
        if not key:
            raise ValueError("两张表没有可用于配对的公共列")
        return run_bridge(job_id, user_id, "compare.run", {**base, "key": key})
    if action == "web.invoice":
        paths = [str(path) for path in payload.get("paths", []) if path]
        if not paths:
            raise ValueError("请上传至少一个 PDF 发票文件")
        root = os.path.commonpath(paths)
        if os.path.isfile(root):
            root = os.path.dirname(root)
        scanned_envelope = run_bridge(job_id, user_id, "invoice.scan", {"root": root})
        scan = scanned_envelope.get("result", {}) if isinstance(scanned_envelope, dict) else {}
        invoices = scan.get("invoices", []) if isinstance(scan, dict) else []
        rows = payload.get("rows")
        if not isinstance(rows, list):
            include_normal = bool(payload.get("include_normal"))
            rows = [{
                "num": item.get("num"), "date": item.get("date"),
                "seller": item.get("seller"), "item": item.get("item_seed") or "",
                "amount": item.get("amount"), "tax": item.get("tax"),
                "total": item.get("total"), "rate": item.get("rate"),
                "note": item.get("note_seed") or "",
            } for item in invoices if include_normal or item.get("special")]
        if not rows:
            raise ValueError("未识别到增值税专用发票")
        month = str(payload.get("month") or scan.get("suggested_month") or "")
        return run_bridge(job_id, user_id, "invoice.generate", {"scan": scan, "rows": rows, "month": month})
    return run_bridge(job_id, user_id, action, payload)


def collect_result_files(value: object) -> list[dict[str, object]]:
    """从桥接结果提取可下载文件，目录结果递归展开。"""
    found: dict[str, dict[str, object]] = {}

    def add(path_value: str) -> None:
        path = Path(path_value)
        candidates = [path] if path.is_file() else list(path.rglob("*"))[:200] if path.is_dir() else []
        for item in candidates:
            if item.is_file():
                resolved = str(item.resolve())
                found[resolved] = {"name": item.name, "path": resolved, "size": item.stat().st_size}

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str) and os.path.isabs(item) and os.path.exists(item):
            add(item)

    visit(value)
    return list(found.values())


def public_result(value: object) -> object:
    """隐藏服务端绝对路径，只向浏览器返回文件名和业务数据。"""
    if isinstance(value, dict):
        return {key: public_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_result(item) for item in value]
    if isinstance(value, str) and os.path.isabs(value):
        return Path(value).name
    return value


def job_public(row: sqlite3.Row) -> dict[str, object]:
    """把持久化任务转换为浏览器可用结构。"""
    files = json.loads(row["files"] or "[]")
    review_pending = is_review_pending(row)
    return {
        "id": row["id"], "action": row["action"], "title": row["title"],
        "status": row["status"], "progress": row["progress"],
        "logs": json.loads(row["logs"] or "[]"),
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "review_pending": review_pending,
        "files": [{
            "name": item["name"], "size": item["size"],
            "url": f"/api/jobs/{row['id']}/files/{index}",
        } for index, item in enumerate(files)],
    }


def run_web_job(job_id: str, user_id: int, action: str, payload: dict[str, object]) -> None:
    """后台执行 Web 任务并持久化结果。"""
    update_job(job_id, status="running", progress=1)
    try:
        result = execute_action(job_id, user_id, action, payload)
        with DB_LOCK, db() as connection:
            row = connection.execute("SELECT cancelled FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
        if row and row["cancelled"]:
            update_job(job_id, status="cancelled", error="任务已取消")
            return
        files = collect_result_files(result)
        update_job(
            job_id,
            status="completed",
            progress=100,
            result=json.dumps(public_result(result), ensure_ascii=False),
            files=json.dumps(files, ensure_ascii=False),
        )
    except Exception as exc:  # pragma: no cover - 具体业务异常由接口回传
        with DB_LOCK, db() as connection:
            row = connection.execute("SELECT cancelled FROM web_jobs WHERE id = ?", (job_id,)).fetchone()
        update_job(
            job_id,
            status="cancelled" if row and row["cancelled"] else "failed",
            error="任务已取消" if row and row["cancelled"] else str(exc),
        )


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "FYTWeb/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}\n")

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容不是有效 JSON") from exc

    def current_user(self) -> sqlite3.Row | None:
        token = self.headers.get("X-Session-Token", "")
        if not token:
            cookie = self.headers.get("Cookie", "")
            token = next((part.split("=", 1)[1] for part in cookie.split("; ") if part.startswith("fyt_session=")), "")
        if not token:
            return None
        with DB_LOCK, db() as connection:
            return connection.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.expires_at > ? AND u.status = 'approved'",
                (token, int(time.time())),
            ).fetchone()

    def require_user(self, admin: bool = False) -> sqlite3.Row:
        row = self.current_user()
        if row is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "请先登录")
        if admin and row["role"] != "admin":
            raise ApiError(HTTPStatus.FORBIDDEN, "只有管理员可以执行此操作")
        return row

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/api/files/upload":
                self.upload_file()
                return
            body = self.read_json()
            if path == "/api/auth/register":
                self.register(body)
            elif path == "/api/auth/login":
                self.login(body)
            elif path == "/api/auth/logout":
                self.logout()
            elif path == "/api/jobs":
                self.create_job(body)
            elif path.startswith("/api/jobs/") and path.endswith("/review"):
                self.submit_review(path, body)
            elif path.startswith("/api/jobs/") and path.endswith("/cancel"):
                self.cancel_job(path)
            elif path.startswith("/api/admin/users/") and path.endswith("/approve"):
                self.review_user(path, "approved")
            elif path.startswith("/api/admin/users/") and path.endswith("/reject"):
                self.review_user(path, "rejected")
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # pragma: no cover - 兜底日志用于现场诊断
            self.log_message("server error: %r", exc)
            self.send_json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/api/health":
                self.send_json({"status": "ok", "app": "峰运通数据管理系统", "version": "1.2.1", "server_time": now_iso()})
            elif path == "/api/auth/me":
                user = self.current_user()
                if user is None:
                    raise ApiError(HTTPStatus.UNAUTHORIZED, "未登录")
                self.send_json({"user": user_public(user)})
            elif path == "/api/overview":
                user = self.require_user()
                with DB_LOCK, db() as connection:
                    pending = connection.execute("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'").fetchone()["n"]
                    total_users = connection.execute("SELECT COUNT(*) AS n FROM users WHERE status = 'approved'").fetchone()["n"]
                    output_jobs = connection.execute(
                        "SELECT COUNT(*) AS n FROM web_jobs WHERE user_id = ? AND status = 'completed'",
                        (user["id"],),
                    ).fetchone()["n"]
                self.send_json({"user": user_public(user), "features": FEATURES, "metrics": {"pending_users": pending, "approved_users": total_users, "output_jobs": output_jobs}})
            elif path == "/api/dashboard":
                self.dashboard()
            elif path == "/api/admin/users":
                self.require_user(admin=True)
                with DB_LOCK, db() as connection:
                    rows = connection.execute("SELECT * FROM users ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC").fetchall()
                self.send_json({"users": [user_public(row) for row in rows]})
            elif path == "/api/jobs":
                self.list_jobs()
            elif path.startswith("/api/jobs/") and "/files/" in path:
                self.download_job_file(path)
            elif path.startswith("/api/jobs/"):
                self.get_job(path)
            elif path.startswith("/api/"):
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
            else:
                self.serve_static(path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # pragma: no cover
            self.log_message("server error: %r", exc)
            self.send_json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def upload_file(self) -> None:
        user = self.require_user()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        name = safe_name(query.get("name", [""])[0])
        group_id = query.get("group", [uuid.uuid4().hex])[0]
        if not group_id.replace("-", "").isalnum() or len(group_id) > 64:
            raise ApiError(HTTPStatus.BAD_REQUEST, "上传批次编号无效")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "文件大小无效") from exc
        if length <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "上传文件为空")
        if length > MAX_UPLOAD_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "单个文件不能超过 200 MB")
        handle = f"upload:{uuid.uuid4().hex}"
        folder = DATA_ROOT / "users" / str(user["id"]) / "uploads" / group_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        if target.exists():
            target = folder / f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}"
        remaining = length
        with target.open("wb") as stream:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    target.unlink(missing_ok=True)
                    raise ApiError(HTTPStatus.BAD_REQUEST, "文件上传不完整")
                stream.write(chunk)
                remaining -= len(chunk)
        with DB_LOCK, db() as connection:
            connection.execute(
                "INSERT INTO uploads(handle, user_id, group_id, name, path, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (handle, user["id"], group_id, name, str(target), length, now_iso()),
            )
        self.send_json({
            "handle": handle, "group": f"upload-group:{group_id}",
            "name": name, "size": length,
        }, HTTPStatus.CREATED)

    def create_job(self, body: dict[str, object]) -> None:
        user = self.require_user()
        action = str(body.get("action") or "")
        if action not in WEB_ACTIONS:
            raise ApiError(HTTPStatus.BAD_REQUEST, "该功能未开放 Web 任务接口")
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数必须是对象")
        try:
            resolved = resolve_uploads(payload, int(user["id"]))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        job_id = uuid.uuid4().hex
        title = str(body.get("title") or action)[:80]
        created = now_iso()
        with DB_LOCK, db() as connection:
            connection.execute(
                "INSERT INTO web_jobs(id, user_id, action, title, status, payload, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)",
                (job_id, user["id"], action, title, json.dumps(payload, ensure_ascii=False), created, created),
            )
        threading.Thread(
            target=run_web_job,
            args=(job_id, int(user["id"]), action, resolved),
            name=f"web-job-{job_id[:8]}",
            daemon=True,
        ).start()
        self.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)

    def list_jobs(self) -> None:
        user = self.require_user()
        with DB_LOCK, db() as connection:
            rows = connection.execute(
                "SELECT * FROM web_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (user["id"],),
            ).fetchall()
        self.send_json({"jobs": [job_public(row) for row in rows]})

    def dashboard(self) -> None:
        """返回工作台看板所需的聚合数据，所有任务只限当前账号。"""
        user = self.require_user()
        with DB_LOCK, db() as connection:
            job_rows = connection.execute(
                "SELECT * FROM web_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 500",
                (user["id"],),
            ).fetchall()
            status_rows = connection.execute(
                "SELECT status, COUNT(*) AS n FROM web_jobs WHERE user_id = ? GROUP BY status",
                (user["id"],),
            ).fetchall()
            pending_users = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'",
            ).fetchone()["n"]
            approved_users = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'approved'",
            ).fetchone()["n"]

        status_breakdown = {str(row["status"]): int(row["n"]) for row in status_rows}
        review_pending_count = sum(1 for row in job_rows if is_review_pending(row))
        if review_pending_count:
            status_breakdown["completed"] = max(0, status_breakdown.get("completed", 0) - review_pending_count)
            status_breakdown["review"] = review_pending_count
        today = datetime.now(timezone.utc).date()
        trend = {
            (today - timedelta(days=offset)).isoformat():
            {"total": 0, "completed": 0, "failed": 0}
            for offset in range(6, -1, -1)
        }
        feature_counts: dict[str, int] = {}
        for row in job_rows:
            created = str(row["created_at"] or "")[:10]
            if created in trend:
                trend[created]["total"] += 1
                if row["status"] == "completed" and not is_review_pending(row):
                    trend[created]["completed"] += 1
                elif row["status"] == "failed":
                    trend[created]["failed"] += 1
            feature_key = feature_key_for_action(row["action"])
            feature_counts[feature_key] = feature_counts.get(feature_key, 0) + 1

        feature_titles = {item["key"]: item["title"] for item in FEATURES}
        feature_usage = [
            {"key": key, "title": feature_titles.get(key, key), "count": count}
            for key, count in sorted(feature_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:6]
        ]
        recent_jobs = []
        recent_files = []
        for row in job_rows[:8]:
            recent_jobs.append({
                "id": row["id"], "action": row["action"], "title": row["title"],
                "status": row["status"], "progress": row["progress"],
                "error": row["error"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "review_pending": is_review_pending(row),
            })
        for row in job_rows:
            if row["status"] != "completed":
                continue
            try:
                files = json.loads(row["files"] or "[]")
            except json.JSONDecodeError:
                files = []
            for index, item in enumerate(files[:5]):
                recent_files.append({
                    "name": item.get("name", "未命名文件"),
                    "size": item.get("size", 0),
                    "url": f"/api/jobs/{row['id']}/files/{index}",
                    "job_id": row["id"], "title": row["title"],
                    "created_at": row["created_at"],
                })
                if len(recent_files) >= 6:
                    break
            if len(recent_files) >= 6:
                break

        self.send_json({
            "user": user_public(user),
            "generated_at": now_iso(),
            "metrics": {
                "pending_users": int(pending_users),
                "approved_users": int(approved_users),
                "total_jobs": sum(status_breakdown.values()),
                "completed_jobs": status_breakdown.get("completed", 0),
                "running_jobs": status_breakdown.get("running", 0) + status_breakdown.get("queued", 0) + status_breakdown.get("review", 0),
                "failed_jobs": status_breakdown.get("failed", 0),
            },
            "status_breakdown": status_breakdown,
            "trend": [{"date": date, **values} for date, values in trend.items()],
            "feature_usage": feature_usage,
            "recent_jobs": recent_jobs,
            "recent_files": recent_files,
        })

    def get_job(self, path: str) -> None:
        user = self.require_user()
        job_id = path.rstrip("/").split("/")[-1]
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT * FROM web_jobs WHERE id = ? AND user_id = ?",
                (job_id, user["id"]),
            ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        self.send_json({"job": job_public(row)})

    def cancel_job(self, path: str) -> None:
        user = self.require_user()
        parts = path.strip("/").split("/")
        job_id = parts[2] if len(parts) >= 4 else ""
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT status FROM web_jobs WHERE id = ? AND user_id = ?",
                (job_id, user["id"]),
            ).fetchone()
            if row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
            connection.execute("UPDATE web_jobs SET cancelled = 1 WHERE id = ?", (job_id,))
        with JOB_LOCK:
            process = JOB_PROCESSES.get(job_id)
        if process and process.poll() is None:
            process.terminate()
        self.send_json({"message": "已请求取消任务"})

    def submit_review(self, path: str, body: dict[str, object]) -> None:
        """提交人工复核选择，并让同一任务继续执行最终业务动作。"""
        user = self.require_user()
        parts = path.strip("/").split("/")
        job_id = parts[2] if len(parts) >= 4 else ""
        choices = body.get("choices")
        if not isinstance(choices, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "复核选择必须是对象")
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT * FROM web_jobs WHERE id = ? AND user_id = ?",
                (job_id, user["id"]),
            ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        action = str(row["action"])
        if action not in REVIEW_ACTIONS or row["status"] != "completed":
            raise ApiError(HTTPStatus.BAD_REQUEST, "该任务当前不可复核")
        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数已损坏，无法继续复核") from exc
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "任务参数已损坏，无法继续复核")

        final_action = REVIEW_ACTIONS[action]
        if action == "web.invoice.review":
            rows = choices.get("rows")
            if not isinstance(rows, list) or not rows:
                raise ApiError(HTTPStatus.BAD_REQUEST, "请至少保留一张发票")
            payload["rows"] = rows
            payload["month"] = str(choices.get("month") or payload.get("month") or "")
            payload["include_normal"] = bool(choices.get("include_normal"))
        elif action == "web.compare.review":
            key = str(choices.get("key") or "")
            if not key:
                raise ApiError(HTTPStatus.BAD_REQUEST, "请选择表格比对关键列")
            payload["key"] = key
        else:
            payload["choices"] = choices
        try:
            resolved = resolve_uploads(payload, int(user["id"]))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

        created = now_iso()
        with DB_LOCK, db() as connection:
            connection.execute(
                "UPDATE web_jobs SET action = ?, status = 'queued', progress = 0, logs = '[]', result = NULL, error = NULL, files = '[]', cancelled = 0, updated_at = ? WHERE id = ? AND user_id = ?",
                (final_action, created, job_id, user["id"]),
            )
        threading.Thread(
            target=run_web_job,
            args=(job_id, int(user["id"]), final_action, resolved),
            name=f"web-job-review-{job_id[:8]}",
            daemon=True,
        ).start()
        self.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)

    def download_job_file(self, path: str) -> None:
        user = self.require_user()
        parts = path.strip("/").split("/")
        try:
            job_id = parts[2]
            index = int(parts[4])
        except (IndexError, ValueError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "下载地址无效") from exc
        with DB_LOCK, db() as connection:
            row = connection.execute(
                "SELECT files FROM web_jobs WHERE id = ? AND user_id = ?",
                (job_id, user["id"]),
            ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        files = json.loads(row["files"] or "[]")
        if index < 0 or index >= len(files):
            raise ApiError(HTTPStatus.NOT_FOUND, "结果文件不存在")
        item = files[index]
        target = Path(item["path"])
        if not target.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "结果文件已被移动或删除")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(item['name'])}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as stream:
            shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)

    def register(self, body: dict[str, object]) -> None:
        username = str(body.get("username", "")).strip().lower()
        display_name = str(body.get("display_name", "")).strip()
        password = str(body.get("password", ""))
        if not (3 <= len(username) <= 32) or not username.replace("_", "").replace("-", "").isalnum():
            raise ApiError(HTTPStatus.BAD_REQUEST, "账号需为 3-32 位字母、数字、下划线或短横线")
        if len(password) < 8:
            raise ApiError(HTTPStatus.BAD_REQUEST, "密码至少 8 位")
        if not display_name:
            display_name = username
        salt, digest = hash_password(password)
        try:
            with DB_LOCK, db() as connection:
                connection.execute("INSERT INTO users(username, display_name, salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)", (username, display_name[:40], salt, digest, now_iso()))
        except sqlite3.IntegrityError as exc:
            raise ApiError(HTTPStatus.CONFLICT, "账号已存在，请直接登录或联系管理员") from exc
        self.send_json({"message": "注册申请已提交，请等待管理员审核"}, HTTPStatus.CREATED)

    def login(self, body: dict[str, object]) -> None:
        username = str(body.get("username", "")).strip().lower()
        password = str(body.get("password", ""))
        with DB_LOCK, db() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not verify_password(password, row["salt"], row["password_hash"]):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "账号或密码不正确")
        if row["status"] == "pending":
            raise ApiError(HTTPStatus.FORBIDDEN, "账号正在等待管理员审核")
        if row["status"] == "rejected":
            raise ApiError(HTTPStatus.FORBIDDEN, "注册申请未通过，请联系管理员")
        token = secrets.token_urlsafe(36)
        with DB_LOCK, db() as connection:
            connection.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)", (token, row["id"], int(time.time()) + SESSION_DAYS * 86400))
        self.send_json({"token": token, "user": user_public(row)})

    def logout(self) -> None:
        token = self.headers.get("X-Session-Token", "")
        with DB_LOCK, db() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.send_json({"message": "已退出登录"})

    def review_user(self, path: str, status: str) -> None:
        actor = self.require_user(admin=True)
        try:
            user_id = int(path.split("/")[4])
        except (IndexError, ValueError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "用户编号无效") from exc
        with DB_LOCK, db() as connection:
            target = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if target is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "用户不存在")
            if target["role"] == "admin":
                raise ApiError(HTTPStatus.BAD_REQUEST, "不能审核管理员账号")
            connection.execute("UPDATE users SET status = ?, approved_at = ? WHERE id = ?", (status, now_iso() if status == "approved" else None, user_id))
            connection.execute("INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)", (actor["id"], status, user_id, now_iso()))
        self.send_json({"message": "已更新用户状态"})

    def serve_static(self, path: str) -> None:
        if not STATIC_ROOT.exists():
            self.send_json({"error": "前端尚未构建，请运行 web-app\\npm run build"}, HTTPStatus.NOT_FOUND)
            return
        relative = path.lstrip("/") or "index.html"
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT not in candidate.parents and candidate != STATIC_ROOT:
            raise ApiError(HTTPStatus.NOT_FOUND, "资源不存在")
        if not candidate.is_file():
            candidate = STATIC_ROOT / "index.html"
        content = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[完成] 峰运通 Web 服务已启动: http://{HOST}:{PORT}")
    print("[提示] 默认管理员账号: admin / admin123456（请上线前通过 FYT_ADMIN_PASSWORD 修改）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[完成] 服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
