"""Web 公开数据投影回归测试。"""

from __future__ import annotations

import json
import sqlite3
import unittest

from web_backend import presenters


class PresenterTests(unittest.TestCase):
    """保护图片受控地址、历史分类清洗和逐记录权限协议。"""

    @staticmethod
    def _row(**values):
        """使用真实 ``sqlite3.Row`` 构造与生产查询一致的映射记录。"""
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row  # 使用真实 Row 类型
        columns = list(values)
        connection.execute(
            "CREATE TABLE sample (%s)" % ", ".join(f'"{column}"' for column in columns)
        )
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            "INSERT INTO sample VALUES (%s)" % placeholders,
            tuple(values[column] for column in columns),
        )
        row = connection.execute("SELECT * FROM sample").fetchone()
        connection.close()
        return row

    def test_daily_source_maps_numeric_image_id_to_controlled_url(self):
        """记录内数字图片编号也必须命中顶层图片，并只返回受权限控制的 URL。"""
        row = self._row(
            id="upload01",
            kind="safety",
            report_date="2026-08-13",
            data_month="2026-08",
            original_name="安全检查.xlsx",
            size=100,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            summary=json.dumps({
                "images": [{"id": 7, "file_name": "现场 图.png"}],
                "records": [{"images": [{"id": 7}]}],
            }, ensure_ascii=False),
            uploaded_by=1,
            uploaded_by_name="管理员",
            created_at="2026-08-13T00:00:00+00:00",
            updated_at="2026-08-13T00:00:00+00:00",
        )
        result = presenters.daily_source_upload_public(row)
        expected = "/api/admin/daily-source-uploads/upload01/images/%E7%8E%B0%E5%9C%BA%20%E5%9B%BE.png"
        self.assertEqual(result["summary"]["images"][0]["url"], expected)  # 顶层图片映射受控 URL
        self.assertEqual(result["summary"]["records"][0]["images"][0]["url"], expected)  # 记录内图片同源映射

    def test_library_filters_legacy_category_and_limits_team_leader_edits(self):
        """淘汰分类回退为未知，班组长查看他人文件时不得获得修改权限。"""
        row = self._row(
            id="file01", name="资料.xlsx", size=20, content_type="application/octet-stream",
            description="", scope="team", category="已淘汰分类",
            categories=json.dumps(["已淘汰分类", "arrival_plan"]), confidence=80,
            signals="[]", sheet="Sheet1", category_sheets="{}",
            created_at="2026-08-13T00:00:00+00:00", updated_at="2026-08-13T00:00:00+00:00",
            owner_id=2, owner_username="member", owner_display_name="成员",
            updated_by=None, editor_username="", editor_display_name="",
        )
        user = self._row(id=1, role="team_leader")
        result = presenters.library_file_public(row, user)
        self.assertEqual(result["category"], "unknown")  # 淘汰分类回退
        self.assertIn("arrival_plan", result["categories"])  # 有效分类保留
        self.assertEqual(
            result["permissions"],
            {"can_download": True, "can_edit": False, "can_replace": False, "can_delete": False},
        )  # 班组长不可编辑他人文件


if __name__ == "__main__":
    unittest.main()
