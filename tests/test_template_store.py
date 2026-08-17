# -*- coding: utf-8 -*-
"""模板中心版本、差异和迁移规则测试。"""
import os
import tempfile
import unittest

from core import template_store


class TestTemplateStore(unittest.TestCase):
    """验证模板指纹版本、结构差异、迁移规则和删除。"""

    def setUp(self):
        """创建隔离模板索引。"""

        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_template_")
        self.path = os.path.join(self.tmp.name, "templates.json")

    def tearDown(self):
        """恢复模板路径并删除临时版本记录。"""

        self.tmp.cleanup()

    def test_same_structure_does_not_create_duplicate_version(self):
        first = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        second = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        self.assertEqual(first["id"], second["id"])  # 同结构复用模板 ID
        self.assertEqual(len(second["versions"]), 1)  # 不产生重复版本
        self.assertEqual(second["versions"][0]["diff"]["summary"], "初始版本")

    def test_structure_change_creates_version_and_diff(self):
        """表头结构变化应创建新版本，并给出新增、删除或改名差异。"""

        template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        updated = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "部门", "公司", "总工时"], path=self.path)
        self.assertEqual(len(updated["versions"]), 2)  # 结构变化新增版本
        latest = updated["versions"][0]
        self.assertEqual(latest["version"], 2)
        self.assertIn("部门", latest["diff"]["added"])  # 新增列进入差异
        self.assertIn("工时", latest["diff"]["removed"])  # 删除列进入差异

    def test_migration_rule_and_apply(self):
        """版本迁移规则应持久化，并把旧字段映射到新模板结构。"""

        saved = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "工时"], path=self.path)
        rule = template_store.save_migration_rule(
            saved["id"], 1, 2,
            {"rename": {"工时": "总工时"}, "defaults": ["部门"]}, path=self.path)
        self.assertEqual(rule["to"], 2)  # 规则目标版本正确
        self.assertEqual(template_store.apply_migration(
            ["姓名", "工时"], rule["rules"]), ["姓名", "总工时", "部门"])  # 旧字段按规则迁移
        self.assertEqual(len(template_store.get_template(saved["id"], self.path)["rules"]), 1)  # 规则已持久化

    def test_delete_and_clear(self):
        first = template_store.save_template(
            "A", "rec_zong", "总表", ["姓名"], path=self.path)
        template_store.save_template("B", "rec_source", "Sheet1", ["姓名"], path=self.path)
        self.assertTrue(template_store.delete_template(first["id"], self.path))  # 删除指定模板
        self.assertEqual(template_store.clear_templates(self.path), 1)  # 清空后仅剩一条


if __name__ == "__main__":
    unittest.main()
