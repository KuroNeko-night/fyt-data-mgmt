# -*- coding: utf-8 -*-
"""Web 服务认证、角色矩阵、会话与管理员账号回归测试。"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime

import web_server

from tests.web_server_test_base import WebServerTestBase


class WebServerAuthTests(WebServerTestBase):
    """登录、锁定、会话撤销、角色矩阵与管理闭环的 HTTP 回归。"""

    def test_requires_login(self):
        """健康检查允许匿名访问，其余业务总览必须拒绝未登录请求。"""

        status, health = self.call("/api/health")
        self.assertEqual(status, 200)  # 健康检查匿名可访问
        self.assertEqual(health["version"], web_server.VERSION)  # 版本一致
        status, payload = self.call("/api/overview")
        self.assertEqual(status, 401)  # 未登录拒绝
        self.assertEqual(payload["error"], "请先登录")  # 统一错误文案

    def test_http_context_json_and_static_cache_policy(self):
        """验证损坏 JSON、Cookie 会话、SPA 回退和分层静态缓存策略。"""

        status, payload = self.call(
            "/api/auth/login",
            token="",
            raw=b"[",
            headers={"Content-Length": "1"},
        )
        self.assertEqual(status, 400)  # 损坏 JSON 拒绝
        self.assertEqual(payload["error"], "请求内容不是有效 JSON")

        login_data = json.dumps({
            "username": "admin",
            "password": "admin123456",
        }).encode("utf-8")
        login_request = urllib.request.Request(
            self.base + "/api/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(login_request, timeout=10) as response:
            cookie = str(response.headers["Set-Cookie"]).split(";", 1)[0]  # 提取会话 Cookie
        me_request = urllib.request.Request(
            self.base + "/api/auth/me",
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(me_request, timeout=10) as response:
            self.assertEqual(json.loads(response.read())["user"]["username"], "admin")  # Cookie 会话有效

        status, missing = self.call("/")
        self.assertEqual(status, 404)  # 前端未构建
        self.assertIn("前端尚未构建", missing["error"])

        assets = web_server.STATIC_ROOT / "assets"
        assets.mkdir(parents=True)
        (web_server.STATIC_ROOT / "index.html").write_text(
            "<main>峰运通</main>", encoding="utf-8",
        )
        (assets / "app-123.js").write_text("window.fyt = true", encoding="utf-8")
        (web_server.STATIC_ROOT / "logo.txt").write_text("FYT", encoding="utf-8")

        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            self.assertEqual(
                response.headers["Cache-Control"],
                "no-store, must-revalidate, no-transform",
            )  # 入口禁止缓存
            self.assertIn("峰运通", response.read().decode("utf-8"))
        with urllib.request.urlopen(self.base + "/assets/app-123.js", timeout=10) as response:
            self.assertEqual(
                response.headers["Cache-Control"],
                "public, max-age=31536000, immutable",
            )  # 带哈希资源长缓存
        with urllib.request.urlopen(self.base + "/logo.txt", timeout=10) as response:
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=604800")  # 普通资源周缓存
        with urllib.request.urlopen(self.base + "/client/route", timeout=10) as response:
            self.assertEqual(
                response.headers["Cache-Control"],
                "no-store, must-revalidate, no-transform",
            )  # SPA 回退也禁缓存
            self.assertIn("峰运通", response.read().decode("utf-8"))

    def test_admin_data_account_and_notifications(self):
        """管理员可维护账号、查看数据摘要并向指定用户或全局发布通知。"""

        status, _ = self.call("/api/auth/register", {
            "username": "member_one", "display_name": "成员一", "password": "password123",
        })
        self.assertEqual(status, 201)  # 注册成功
        status, users = self.call("/api/admin/users", token=self.admin)
        self.assertEqual(status, 200)  # 管理员可取用户列表
        member = next(item for item in users["users"] if item["username"] == "member_one")
        status, _ = self.call(f"/api/admin/users/{member['id']}/approve", token=self.admin, payload={})
        self.assertEqual(status, 200)  # 审核通过
        status, _ = self.call(f"/api/admin/users/{member['id']}", {
            "display_name": "成员一（已更新）", "status": "approved",
        }, token=self.admin, method="PATCH")
        self.assertEqual(status, 200)  # 更新用户成功
        status, _ = self.call("/api/admin/messages", {
            "user_id": member["id"], "title": "定向提醒", "content": "请查看本周数据。",
        }, token=self.admin)
        self.assertEqual(status, 201)  # 定向通知创建
        status, _ = self.call("/api/admin/announcements", {
            "title": "全局公告", "content": "系统将在周末维护。",
        }, token=self.admin)
        self.assertEqual(status, 201)  # 全局公告创建
        status, data = self.call("/api/admin/data", token=self.admin)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["summary"]["approved_users"], 2)  # 审核用户数
        member_token = self.call("/api/auth/login", {"username": "member_one", "password": "password123"})[1]["token"]  # 成员登录
        status, _ = self.call("/api/admin/data", token=member_token)
        self.assertEqual(status, 403)  # 成员访问管理数据被拒
        status, board = self.call("/api/dashboard", token=member_token)
        self.assertEqual(status, 200)  # 工作台可访问
        self.assertEqual({item["title"] for item in board["notifications"]}, {"定向提醒", "全局公告"})  # 两类通知
        status, inbox = self.call("/api/notifications", token=member_token)
        self.assertEqual(status, 200)
        self.assertEqual(inbox["unread_count"], 2)  # 两条未读
        announcement = next(item for item in inbox["notifications"] if item["kind"] == "announcement")
        status, _ = self.call(f"/api/notifications/announcement/{announcement['id']}/read", token=member_token, payload={})
        self.assertEqual(status, 200)  # 单条已读
        status, inbox = self.call("/api/notifications", token=member_token)
        self.assertEqual(inbox["unread_count"], 1)  # 剩余一条未读
        status, _ = self.call("/api/notifications/read-all", token=member_token, payload={})
        self.assertEqual(status, 200)  # 全部已读
        status, inbox = self.call("/api/notifications", token=member_token)
        self.assertEqual(inbox["unread_count"], 0)  # 清零
        status, _ = self.call(f"/api/admin/users/{member['id']}", token=self.admin, method="DELETE")
        self.assertEqual(status, 200)  # 删除用户
        status, _ = self.call("/api/auth/me", token=member_token)
        self.assertEqual(status, 401)  # 会话失效

    def test_admin_role_access_sessions_and_audit(self):
        """角色授予、管理入口、会话撤销和审计记录必须形成一致的管理员闭环。"""

        status, _ = self.call("/api/auth/register", {
            "username": "manager_one", "display_name": "管理员候选", "password": "password123",
        })
        self.assertEqual(status, 201)
        status, users = self.call("/api/admin/users", token=self.admin)
        self.assertEqual(status, 200)
        member = next(item for item in users["users"] if item["username"] == "manager_one")
        primary = next(item for item in users["users"] if item["username"] == "admin")
        status, _ = self.call(f"/api/admin/users/{member['id']}/approve", token=self.admin, payload={})
        self.assertEqual(status, 200)
        member_token = self.call(
            "/api/auth/login", {"username": "manager_one", "password": "password123"},
        )[1]["token"]

        status, payload = self.call(
            f"/api/admin/users/{member['id']}/role", {"role": "admin"}, token=self.admin,
        )
        self.assertEqual(status, 200)
        self.assertIn("管理员权限", payload["message"])
        status, _ = self.call("/api/admin/data", token=member_token)
        self.assertEqual(status, 200)

        status, _ = self.call(
            f"/api/admin/users/{member['id']}/role", {"role": "user"}, token=member_token,
        )
        self.assertEqual(status, 400)
        status, _ = self.call(
            f"/api/admin/users/{primary['id']}/role", {"role": "user"}, token=member_token,
        )
        self.assertEqual(status, 400)

        status, _ = self.call(
            f"/api/admin/users/{member['id']}/role", {"role": "user"}, token=self.admin,
        )
        self.assertEqual(status, 200)
        status, _ = self.call("/api/admin/data", token=member_token)
        self.assertEqual(status, 403)
        status, payload = self.call(
            f"/api/admin/users/{member['id']}/sessions/revoke", {}, token=self.admin,
        )
        self.assertEqual(status, 200)
        self.assertIn("1 个登录会话", payload["message"])
        status, _ = self.call("/api/auth/me", token=member_token)
        self.assertEqual(status, 401)

        status, _ = self.call(
            f"/api/admin/users/{member['id']}/access", {"enabled": False}, token=self.admin,
        )
        self.assertEqual(status, 200)
        status, payload = self.call(
            "/api/auth/login", {"username": "manager_one", "password": "password123"},
        )
        self.assertEqual(status, 403)
        self.assertIn("暂停", payload["error"])
        status, data = self.call("/api/admin/data", token=self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(data["summary"]["disabled_users"], 1)

        status, _ = self.call(
            f"/api/admin/users/{member['id']}/access", {"enabled": True}, token=self.admin,
        )
        self.assertEqual(status, 200)
        restored_token = self.call(
            "/api/auth/login", {"username": "manager_one", "password": "password123"},
        )[1]["token"]
        status, _ = self.call("/api/admin/audit", token=restored_token)
        self.assertEqual(status, 403)
        status, payload = self.call("/api/admin/audit", token=self.admin)
        self.assertEqual(status, 200)
        actions = {item["action"] for item in payload["audit"]}
        self.assertTrue({
            "grant_admin", "revoke_admin", "revoke_sessions", "disable_user", "enable_user",
        }.issubset(actions))

    def test_login_lock_password_change_and_device_sessions(self):
        """连续登录失败触发锁定，改密后旧设备会话应按安全规则失效。"""

        for attempt in range(web_server.LOGIN_FAILURE_LIMIT):
            status, payload = self.call(
                "/api/auth/login", {"username": "admin", "password": "wrong-password1"},
            )
            self.assertEqual(status, 429 if attempt == web_server.LOGIN_FAILURE_LIMIT - 1 else 401)
        status, payload = self.call(
            "/api/auth/login", {"username": "admin", "password": "admin123456"},
        )
        self.assertEqual(status, 429)
        self.assertIn("分钟后重试", payload["error"])

        with web_server.DB_LOCK, web_server.db() as connection:
            connection.execute("DELETE FROM login_attempts")
        status, second = self.call(
            "/api/auth/login", {"username": "admin", "password": "admin123456"},
            headers={"User-Agent": "FYT-Test-Device-2"},
        )
        self.assertEqual(status, 200)
        second_token = second["token"]
        status, payload = self.call("/api/auth/sessions", token=second_token)
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["sessions"]), 2)
        self.assertEqual(sum(bool(item["current"]) for item in payload["sessions"]), 1)

        status, payload = self.call("/api/auth/password", {
            "current_password": "admin123456", "new_password": "NewPassword2026",
        }, token=second_token)
        self.assertEqual(status, 200)
        self.assertIn("其他设备已退出", payload["message"])
        self.assertEqual(self.call("/api/auth/me", token=self.admin)[0], 401)
        self.assertEqual(self.call("/api/auth/me", token=second_token)[0], 200)
        self.assertEqual(self.call(
            "/api/auth/login", {"username": "admin", "password": "admin123456"},
        )[0], 401)
        self.assertEqual(self.call(
            "/api/auth/login", {"username": "admin", "password": "NewPassword2026"},
        )[0], 200)

    def test_admin_password_reset_revokes_target_sessions(self):
        """管理员重置他人密码后必须撤销该账号全部现有会话。"""

        self.call("/api/auth/register", {
            "username": "reset_member", "display_name": "待重置成员", "password": "password123",
        })
        member = next(item for item in self.call("/api/admin/users", token=self.admin)[1]["users"] if item["username"] == "reset_member")
        self.call(f"/api/admin/users/{member['id']}/approve", {}, token=self.admin)
        member_token = self.call(
            "/api/auth/login", {"username": "reset_member", "password": "password123"},
        )[1]["token"]
        status, payload = self.call(
            f"/api/admin/users/{member['id']}/password",
            {"password": "ResetPassword2026"}, token=self.admin,
        )
        self.assertEqual(status, 200)
        self.assertIn("1 个登录会话", payload["message"])
        self.assertEqual(self.call("/api/auth/me", token=member_token)[0], 401)
        self.assertEqual(self.call(
            "/api/auth/login", {"username": "reset_member", "password": "ResetPassword2026"},
        )[0], 200)

    def test_role_matrix_and_workshop_edit_scope(self):
        """成员、班组长和管理员的导航/API 权限及现场问题编辑范围必须匹配角色矩阵。"""

        accounts = {}
        for username, display_name, role in (
            ("role_leader", "班组长甲", "team_leader"),
            ("role_member", "业务成员甲", "user"),
        ):
            self.assertEqual(self.call("/api/auth/register", {
                "username": username, "display_name": display_name, "password": "password123",
            })[0], 201)
            account = next(
                item for item in self.call("/api/admin/users", token=self.admin)[1]["users"]
                if item["username"] == username
            )
            self.assertEqual(
                self.call(f"/api/admin/users/{account['id']}/approve", {}, token=self.admin)[0],
                200,
            )
            if role != "user":
                status, payload = self.call(
                    f"/api/admin/users/{account['id']}/role",
                    {"role": role}, token=self.admin,
                )
                self.assertEqual(status, 200)
                self.assertIn("班组长", payload["message"])
            accounts[username] = self.call("/api/auth/login", {
                "username": username, "password": "password123",
            })[1]["token"]

        leader = accounts["role_leader"]
        member = accounts["role_member"]
        self.assertEqual(self.call("/api/auth/me", token=leader)[1]["user"]["role"], "team_leader")
        self.assertEqual(self.call("/api/daily-report?date=2026-08-08", token=leader)[0], 403)
        self.assertEqual(self.call("/api/daily-report?date=2026-08-08", token=member)[0], 403)
        query = urllib.parse.quote("不存在的批次")
        self.assertEqual(self.call(f"/api/batch-track?q={query}", token=leader)[0], 200)
        self.assertEqual(self.call(f"/api/batch-track?q={query}", token=member)[0], 403)
        self.assertEqual(self.call("/api/reports?range=7d", token=leader)[0], 403)
        self.assertEqual(self.call("/api/reports?range=7d", token=member)[0], 403)
        self.assertEqual(self.call("/api/library/files", token=leader)[0], 200)
        self.assertEqual(self.call("/api/library/files", token=member)[0], 403)

        issue_date = datetime.now().strftime("%Y-%m-%d")
        issue_payload = {
            "issue_date": issue_date,
            "category": "error_proofing",
            "cause": "班组长发布的现场问题",
            "happened_at": "08:30",
            "tracking_status": "处理中",
            "responsible_person": "班组长甲",
        }
        status, created = self.call("/api/workshop/issues", issue_payload, token=leader)
        self.assertEqual(status, 201)
        issue_id = created["issue"]["id"]
        self.assertEqual(self.call(f"/api/workshop/issues/{issue_id}/publish", {}, token=leader)[0], 200)
        published_issue = next(
            item for item in self.call(f"/api/workshop/issues?date={issue_date}", token=leader)[1]["issues"]
            if item["id"] == issue_id
        )
        listed = self.call(f"/api/workshop/issues?date={issue_date}", token=member)[1]
        visible = next(item for item in listed["issues"] if item["id"] == issue_id)
        self.assertFalse(visible["permissions"]["can_edit"])
        self.assertFalse(visible["permissions"]["can_resolve"])
        self.assertEqual(self.call(
            f"/api/workshop/issues/{issue_id}",
            {"cause": "普通成员不能修改班组长已发布问题", "expected_updated_at": visible["updated_at"]},
            token=member, method="PATCH",
        )[0], 403)
        self.assertEqual(self.call(
            f"/api/workshop/issues/{issue_id}",
            {"cause": "班组长已修正现场问题", "expected_updated_at": published_issue["updated_at"]},
            token=leader, method="PATCH",
        )[0], 200)

    def test_login_failure_lock_configurable(self):
        """登录失败阈值和锁定时长应服从配置，同时保持原子计数。"""

        original = (web_server.LOGIN_FAILURE_LIMIT, web_server.LOGIN_LOCK_SECONDS)
        try:
            web_server.LOGIN_FAILURE_LIMIT = 3
            web_server.LOGIN_LOCK_SECONDS = 300
            for _ in range(3):
                status, _ = self.call("/api/auth/login", {"username": "admin", "password": "wrong-pass-123"})
                self.assertIn(status, (401, 429))
            status, payload = self.call("/api/auth/login", {"username": "admin", "password": "wrong-pass-123"})
            self.assertEqual(status, 429)
            self.assertIn("重试", payload["error"])
            # 正确密码也被锁定拦截
            status, _ = self.call("/api/auth/login", {"username": "admin", "password": "admin123456"})
            self.assertEqual(status, 429)
        finally:
            web_server.LOGIN_FAILURE_LIMIT, web_server.LOGIN_LOCK_SECONDS = original


if __name__ == "__main__":
    unittest.main()
