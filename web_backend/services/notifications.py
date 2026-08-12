"""消息、公告和已读状态服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any, Callable

from web_backend.errors import ApiError
from web_backend.http.path_params import path_id


@dataclass(frozen=True)
class NotificationDependencies:
    """消息通知服务依赖。"""

    db_lock: Any
    db: Callable[[], Any]
    now_iso: Callable[[], str]
    announcement_public: Callable[[Any], dict[str, object]]
    notification_public: Callable[[Any], dict[str, object]]


def list_admin_announcements(handler: Any, deps: NotificationDependencies) -> None:
    """返回最近的全局公告，供管理员维护。"""
    handler.require_user(admin=True)
    with deps.db_lock, deps.db() as connection:
        rows = connection.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    handler.send_json({"announcements": [deps.announcement_public(row) for row in rows]})

def notifications(handler: Any, deps: NotificationDependencies) -> None:
    """合并当前账号可见的公告和定向消息，并计算未读数量。"""
    user = handler.require_user()
    now = deps.now_iso()  # 同一响应使用统一时间点，避免公告过期边界在两次查询间发生变化。
    with deps.db_lock, deps.db() as connection:
        announcements = connection.execute(  # 左连接当前账号的阅读记录，未读公告的 read_at 保持 NULL。
            "SELECT a.id, a.title, a.content, a.created_at, a.expires_at, a.active, r.read_at "
            "FROM announcements a LEFT JOIN announcement_reads r "
            "ON r.announcement_id = a.id AND r.user_id = ? "
            "WHERE active = 1 AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?) "
            "ORDER BY created_at DESC LIMIT 20", (user["id"], now)
        ).fetchall()
        messages = connection.execute(  # recipient_user_id 在 SQL 层过滤，不能依赖前端隐藏他人私信。
            "SELECT id, title, content, created_at, read_at FROM messages WHERE recipient_user_id = ? "
            "ORDER BY created_at DESC LIMIT 20", (user["id"],)
        ).fetchall()
    items = [deps.notification_public(row, "announcement") for row in announcements]
    items.extend(deps.notification_public(row, "message") for row in messages)
    items.sort(key=lambda item: str(item["created_at"]), reverse=True)  # 两类数据合并后重新按统一时间轴排序。
    items = items[:30]  # 每类最多取 20 条，最终限制 30 条以控制首屏负载。
    handler.send_json({"notifications": items, "unread_count": sum(1 for item in items if not item["read_at"])})

def mark_notification_read(handler: Any, path: str, deps: NotificationDependencies) -> None:
    """按通知类型写入已读状态，并确保账号只能操作自己的私信。

    私信通过接收账号条件原子更新，公告则写入账号与公告关联表；重复标记公告会更新时间
    而不新增重复记录。路径结构、类型和数字编号均先校验，无权限私信按不存在处理。
    """
    user = handler.require_user()
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[1] != "notifications" or parts[4] != "read":  # 拒绝额外路径段，避免宽松解析错误命中动作。
        raise ApiError(HTTPStatus.BAD_REQUEST, "消息地址无效")
    kind = parts[2]
    try:
        item_id = int(parts[3])
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "消息编号无效") from exc
    read_at = deps.now_iso()
    with deps.db_lock, deps.db() as connection:
        if kind == "message":
            changed = connection.execute("UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE id = ? AND recipient_user_id = ?", (read_at, item_id, user["id"])).rowcount
        elif kind == "announcement":  # 公告是全局记录，已读状态单独保存在账号关联表中。
            exists = connection.execute("SELECT 1 FROM announcements WHERE id = ? AND active = 1", (item_id,)).fetchone()
            if exists is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "公告不存在")
            connection.execute("INSERT INTO announcement_reads(announcement_id, user_id, read_at) VALUES (?, ?, ?) ON CONFLICT(announcement_id, user_id) DO UPDATE SET read_at = excluded.read_at", (item_id, user["id"], read_at))
            changed = 1
        else:
            raise ApiError(HTTPStatus.BAD_REQUEST, "消息类型无效")
    if not changed:
        raise ApiError(HTTPStatus.NOT_FOUND, "消息不存在")
    handler.send_json({"message": "已标记为已读", "read_at": read_at})

def mark_all_notifications_read(handler: Any, deps: NotificationDependencies) -> None:
    """在同一事务中标记全部私信和当前仍有效的公告。"""
    user = handler.require_user()
    read_at = deps.now_iso()
    now = deps.now_iso()
    with deps.db_lock, deps.db() as connection:  # 两类通知一起提交，避免出现一类已读、另一类仍未读的半完成状态。
        connection.execute("UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE recipient_user_id = ?", (read_at, user["id"]))
        connection.execute("INSERT INTO announcement_reads(announcement_id, user_id, read_at) SELECT id, ?, ? FROM announcements WHERE active = 1 AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?) ON CONFLICT(announcement_id, user_id) DO UPDATE SET read_at = excluded.read_at", (user["id"], read_at, now))
    handler.send_json({"message": "全部消息已读"})

def publish_message(handler: Any, body: dict[str, object], deps: NotificationDependencies) -> None:
    """向一个正常使用的账号发布定向消息并记录管理审计。

    接收者必须由内部数字编号定位且处于已通过状态，避免向已删除、待审核或已暂停账号
    累积不可见消息。标题和正文分别限制长度，保护通知列表负载和数据库体积。
    """
    actor = handler.require_user(admin=True)  # 发布者身份只能来自服务端会话，不能信任请求体中的账号信息。
    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "请选择接收账号") from exc
    title = str(body.get("title") or "").strip()
    content = str(body.get("content") or "").strip()
    if not title or len(title) > 80 or not content or len(content) > 4000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "消息标题或内容长度不符合要求")
    with deps.db_lock, deps.db() as connection:
        target = connection.execute("SELECT id, status FROM users WHERE id = ?", (user_id,)).fetchone()  # 写消息前确认目标存在且状态允许接收。
        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "接收账号不存在")
        if target["status"] != "approved":
            raise ApiError(HTTPStatus.BAD_REQUEST, "只能向正常使用的账号发布消息")
        connection.execute("INSERT INTO messages(recipient_user_id, title, content, created_by, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, title, content, actor["id"], deps.now_iso()))
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)",
            (actor["id"], "publish_message", user_id, deps.now_iso()),
        )
    handler.send_json({"message": "定向消息已发布"}, HTTPStatus.CREATED)

def publish_announcement(handler: Any, body: dict[str, object], deps: NotificationDependencies) -> None:
    """发布一条可选截止时间的全局公告。

    截止时间保留客户端提交的带时区 ISO 文本，列表查询使用同一 ISO 时间体系判断是否
    过期。空截止时间保存为 ``NULL``，明确表示长期有效，而不是依赖空字符串排序规则。
    """
    actor = handler.require_user(admin=True)
    title = str(body.get("title") or "").strip()
    content = str(body.get("content") or "").strip()
    expires_at = str(body.get("expires_at") or "").strip() or None  # 空值落为 NULL，表示公告长期有效。
    if not title or len(title) > 80 or not content or len(content) > 4000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "公告标题或内容长度不符合要求")
    if expires_at:
        try:
            datetime.fromisoformat(expires_at.replace("Z", "+00:00"))  # 兼容浏览器 Z 后缀，同时阻止任意文本进入时间字段。
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "公告截止时间格式无效") from exc
    with deps.db_lock, deps.db() as connection:
        connection.execute("INSERT INTO announcements(title, content, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)", (title, content, actor["id"], deps.now_iso(), expires_at))
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
            (actor["id"], "publish_announcement", deps.now_iso()),
        )
    handler.send_json({"message": "全局公告已发布"}, HTTPStatus.CREATED)

def update_announcement(handler: Any, path: str, body: dict[str, object], deps: NotificationDependencies) -> None:
    """修改公告标题、正文与启用状态，并保留管理审计记录。

    该接口不修改发布时间和原发布者，避免普通编辑改变通知时间轴。长度在落库前截断到
    与发布接口相同的上限，兼容旧客户端没有先做长度校验的情况。
    """
    actor = handler.require_user(admin=True)
    try:
        announcement_id = int(path_id(path, "/api/admin/announcements/"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "公告编号无效") from exc
    title = str(body.get("title") or "").strip()
    content = str(body.get("content") or "").strip()
    active = body.get("active", True)
    if not isinstance(active, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, "公告状态无效")
    if not title or not content:
        raise ApiError(HTTPStatus.BAD_REQUEST, "公告标题和内容不能为空")
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute("UPDATE announcements SET title = ?, content = ?, active = ? WHERE id = ?", (title[:80], content[:4000], int(active), announcement_id)).rowcount
        if changed:
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                (actor["id"], f"update_announcement:{announcement_id}", deps.now_iso()),
            )
    if not changed:
        raise ApiError(HTTPStatus.NOT_FOUND, "公告不存在")
    handler.send_json({"message": "公告已更新"})

def delete_announcement(handler: Any, path: str, deps: NotificationDependencies) -> None:
    """把公告标记为停用而非物理删除。

    软删除保留公告本体、既有已读记录和审计可追溯性；普通通知查询只返回启用公告，
    因而撤下后立即对用户不可见。重复撤下仍会命中记录并保持幂等状态。
    """
    actor = handler.require_user(admin=True)
    try:
        announcement_id = int(path_id(path, "/api/admin/announcements/"))
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "公告编号无效") from exc
    with deps.db_lock, deps.db() as connection:
        changed = connection.execute("UPDATE announcements SET active = 0 WHERE id = ?", (announcement_id,)).rowcount
        if changed:
            connection.execute(
                "INSERT INTO audit_log(actor_id, action, created_at) VALUES (?, ?, ?)",
                (actor["id"], f"disable_announcement:{announcement_id}", deps.now_iso()),
            )
    if not changed:
        raise ApiError(HTTPStatus.NOT_FOUND, "公告不存在")
    handler.send_json({"message": "公告已撤下"})
