# -*- coding: utf-8 -*-
"""主数据档案：供应商编码与材料主数据的持久化与学习。"""
from __future__ import annotations

import os
import tempfile
import unittest

from core import material_catalog


class MaterialCatalogTests(unittest.TestCase):
    """验证主数据库学习、解析、确认值保护、并发预期值和备份。"""

    def setUp(self):
        """创建隔离主数据库文件。"""

        self.temp = tempfile.TemporaryDirectory(prefix="fyt_catalog_")
        os.environ["FYT_CATALOG_PATH"] = os.path.join(self.temp.name, "catalog.json")

    def tearDown(self):
        """恢复环境并删除主数据库及备份。"""

        os.environ.pop("FYT_CATALOG_PATH", None)
        self.temp.cleanup()

    def test_learn_suppliers_and_resolve(self):
        added = material_catalog.learn_suppliers({"客供件": "GYS1", "众瀚": "GYS2"})
        self.assertEqual(added, 2)
        self.assertEqual(material_catalog.resolve_supplier_code("众瀚"), "GYS2")
        self.assertEqual(material_catalog.resolve_supplier_code("不存在"), "")
        # 重复学习不重复计数
        self.assertEqual(material_catalog.learn_suppliers({"客供件": "GYS1"}), 0)
        self.assertEqual(material_catalog.resolve_supplier_code("客供件"), "GYS1")

    def test_learn_materials(self):
        """被动学习应补齐物料名称、规格、单位和供应商，同时保留来源证据。"""

        added = material_catalog.learn_materials([
            {"code": "JBC001", "name": "铁箱", "spec": "100x50", "unit": "个", "supplier": "众瀚"},
        ])
        self.assertEqual(added, 1)
        data = material_catalog.load()
        self.assertEqual(data["materials"]["JBC001"]["name"], "铁箱")
        self.assertEqual(data["materials"]["JBC001"]["supplier"], "众瀚")
        # 被动学习只补空缺，不得覆盖管理员已经确认的正式值
        logs = []
        added = material_catalog.learn_materials([
            {"code": "JBC001", "name": "铁箱", "spec": "100x50", "unit": "个", "supplier": "众瀚", "name": "铁箱-新"},
        ], log=logs.append)
        self.assertEqual(added, 0)
        self.assertEqual(material_catalog.load()["materials"]["JBC001"]["name"], "铁箱")
        self.assertTrue(any("保留管理员确认值" in message for message in logs))

    def test_resolver_only_fills_blanks_and_normalizes_excel_codes(self):
        """解析器规范化 Excel 数字编码，但只补空字段，不覆盖源表已有业务值。"""

        material_catalog.upsert_supplier("测试 供应商", "GYS9")
        material_catalog.upsert_material(
            "123", "主库名称", spec="10×20", unit="个", supplier="测试 供应商")
        resolver = material_catalog.CatalogResolver()
        counts = {}
        additions = resolver.complete_material(
            123.0,
            {"name": "源表名称", "spec": "", "unit": None, "supplier": ""},
            counts=counts,
        )
        self.assertNotIn("name", additions)
        self.assertEqual(additions["spec"], "10×20")
        self.assertEqual(additions["unit"], "个")
        self.assertEqual(additions["supplier"], "测试 供应商")
        self.assertEqual(resolver.resolve_supplier_code("测试　供应商"), "GYS9")
        self.assertEqual(counts, {"spec": 1, "unit": 1, "supplier": 1})

    def test_resolver_does_not_guess_ambiguous_code_alias(self):
        material_catalog.upsert_material("123", "整数编码")
        material_catalog.upsert_material("123.0", "文本小数编码")
        resolver = material_catalog.CatalogResolver()
        self.assertEqual(resolver.resolve_material("１２３"), {})
        self.assertEqual(resolver.resolve_material("123")["name"], "整数编码")
        self.assertEqual(resolver.resolve_material("123.0")["name"], "文本小数编码")

    def test_learn_suppliers_does_not_overwrite_confirmed_code(self):
        material_catalog.upsert_supplier("众瀚", "GYS1")
        logs = []
        added = material_catalog.learn_suppliers({"众瀚": "GYS2"}, log=logs.append)
        self.assertEqual(added, 0)
        self.assertEqual(material_catalog.resolve_supplier_code("众瀚"), "GYS1")
        self.assertTrue(any("保留管理员确认值" in message for message in logs))

    def test_upsert_delete(self):
        """管理员手工维护的供应商和物料关系应支持更新与删除并立即持久化。"""

        material_catalog.upsert_supplier("文恒", "GYS3")
        self.assertEqual(material_catalog.resolve_supplier_code("文恒"), "GYS3")
        material_catalog.upsert_supplier("文恒", "GYS3-NEW")
        self.assertEqual(material_catalog.resolve_supplier_code("文恒"), "GYS3-NEW")
        material_catalog.delete_supplier("文恒")
        self.assertEqual(material_catalog.resolve_supplier_code("文恒"), "")

        material_catalog.upsert_material("JBC002", "托盘", spec="1200x1000", unit="个", supplier="文恒")
        data = material_catalog.load()
        self.assertEqual(data["materials"]["JBC002"]["unit"], "个")
        material_catalog.delete_material("JBC002")
        self.assertNotIn("JBC002", material_catalog.load()["materials"])

    def test_empty_upsert_raises(self):
        with self.assertRaises(ValueError):
            material_catalog.upsert_supplier("", "GYS1")
        with self.assertRaises(ValueError):
            material_catalog.upsert_supplier("名称", "")
        with self.assertRaises(ValueError):
            material_catalog.upsert_material("", "铁箱")

    def test_persistence_across_loads(self):
        material_catalog.learn_suppliers({"吉致": "GYS4"})
        material_catalog.learn_materials([{"code": "JBC003", "name": "珍珠棉", "supplier": "吉致"}])
        data = material_catalog.load()
        self.assertEqual(data["suppliers"]["吉致"], "GYS4")
        self.assertTrue(data["updated_at"])
        # 文件确实落盘且可重复读
        self.assertTrue(os.path.isfile(material_catalog.catalog_path()))
        self.assertEqual(material_catalog.load()["materials"]["JBC003"]["name"], "珍珠棉")

    def test_apply_relations_checks_expected_current_and_creates_backup(self):
        """批量维护使用预期当前值防并发覆盖，成功写入前创建可恢复备份。"""

        material_catalog.upsert_material("JBC004", "旧名称")
        backup_dir = os.path.join(self.temp.name, "backups")
        summary = material_catalog.apply_relations([{
            "relation_type": "material_name",
            "key": "JBC004",
            "value": "新名称",
            "expected_current": "旧名称",
        }], backup_dir=backup_dir)
        self.assertEqual(summary["changed"], 1)
        self.assertTrue(os.path.isfile(summary["backup_path"]))
        self.assertEqual(material_catalog.load()["materials"]["JBC004"]["name"], "新名称")

        with self.assertRaises(material_catalog.CatalogConflictError):
            material_catalog.apply_relations([{
                "relation_type": "material_name",
                "key": "JBC004",
                "value": "再次修改",
                "expected_current": "旧名称",
            }])


if __name__ == "__main__":
    unittest.main()
