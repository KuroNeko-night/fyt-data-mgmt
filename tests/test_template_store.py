# -*- coding: utf-8 -*-
"""模板中心版本、差异和迁移规则测试。"""
import os
import tempfile
import unittest

from core import template_store


class TestTemplateStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fyt_template_")
        self.path = os.path.join(self.tmp.name, "templates.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_structure_does_not_create_duplicate_version(self):
        first = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        second = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(second["versions"]), 1)
        self.assertEqual(second["versions"][0]["diff"]["summary"], "初始版本")

    def test_structure_change_creates_version_and_diff(self):
        template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "公司", "工时"], path=self.path)
        updated = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "部门", "公司", "总工时"], path=self.path)
        self.assertEqual(len(updated["versions"]), 2)
        latest = updated["versions"][0]
        self.assertEqual(latest["version"], 2)
        self.assertIn("部门", latest["diff"]["added"])
        self.assertIn("工时", latest["diff"]["removed"])

    def test_migration_rule_and_apply(self):
        saved = template_store.save_template(
            "月度总表", "rec_zong", "总表", ["姓名", "工时"], path=self.path)
        rule = template_store.save_migration_rule(
            saved["id"], 1, 2,
            {"rename": {"工时": "总工时"}, "defaults": ["部门"]}, path=self.path)
        self.assertEqual(rule["to"], 2)
        self.assertEqual(template_store.apply_migration(
            ["姓名", "工时"], rule["rules"]), ["姓名", "总工时", "部门"])
        self.assertEqual(len(template_store.get_template(saved["id"], self.path)["rules"]), 1)

    def test_delete_and_clear(self):
        first = template_store.save_template(
            "A", "rec_zong", "总表", ["姓名"], path=self.path)
        template_store.save_template("B", "rec_source", "Sheet1", ["姓名"], path=self.path)
        self.assertTrue(template_store.delete_template(first["id"], self.path))
        self.assertEqual(template_store.clear_templates(self.path), 1)


if __name__ == "__main__":
    unittest.main()
