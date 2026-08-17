# -*- coding: utf-8 -*-
"""圈复杂度检查脚本与 CI 质量门禁的契约回归。"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """以独立模块加载 scripts/check_complexity.py，避免污染测试导入路径。"""
    path = ROOT / "scripts" / "check_complexity.py"
    spec = importlib.util.spec_from_file_location("check_complexity_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ComplexityCheckTests(unittest.TestCase):
    """保护复杂度阈值、变更判定和 CI 门禁不被误改。"""

    def test_rank_thresholds_match_radon_convention(self):
        """A-F 评级必须与 radon 默认阈值一致。"""

        module = _load_script()
        self.assertEqual(module._rank_for(1), "A")
        self.assertEqual(module._rank_for(5), "A")
        self.assertEqual(module._rank_for(6), "B")
        self.assertEqual(module._rank_for(10), "B")
        self.assertEqual(module._rank_for(11), "C")
        self.assertEqual(module._rank_for(20), "C")
        self.assertEqual(module._rank_for(21), "D")
        self.assertEqual(module._rank_for(41), "F")

    def test_python_source_filter_excludes_generated_paths(self):
        """只分析仓库自行维护的 Python 源码，忽略依赖与生成物。"""

        module = _load_script()
        self.assertTrue(module._is_python_source("core/settings.py"))
        self.assertTrue(module._is_python_source("web_backend/services/workshop.py"))
        self.assertFalse(module._is_python_source("web_backend/services/workshop.ts"))
        self.assertFalse(module._is_python_source("dist/deploy/linux/core/settings.py"))
        self.assertFalse(module._is_python_source(".venv/Lib/site-packages/x.py"))

    def test_new_violations_only_flag_new_or_worsened_functions(self):
        """历史超标但未变复杂的函数不应阻塞新提交。"""

        module = _load_script()

        def report(name, complexity):
            return module.BlockReport(
                path="core/example.py", fullname=name, name=name, kind="Function",
                complexity=complexity, rank=module._rank_for(complexity),
                lineno=10, lines=20, is_function=True,
            )

        baseline = {"old_bad": 18, "old_ok": 4}
        reports = [
            report("old_bad", 18),   # 历史超标未恶化，不算新问题
            report("old_ok", 17),    # 基线合规、本次变复杂，应报错
            report("new_bad", 16),   # 新函数超标，应报错
            report("new_ok", 15),    # 等于阈值不报错
        ]
        violations = module._new_violations(reports, baseline, 15)
        self.assertEqual({item[0].name for item in violations}, {"old_ok", "new_bad"})

    def test_workflow_installs_radon_and_uses_baseline_mode(self):
        """CI 必须安装固定版本 radon，并只拦截本次变更新增的超标函数。"""

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("complexity-check", workflow)
        self.assertIn("radon==6.0.1", workflow)
        self.assertIn("check_complexity.py --base", workflow)
        self.assertIn("needs: [repository-hygiene, complexity-check, python-tests, web-build]", workflow)  # 质量门禁在镜像构建之前

    def test_development_requirements_lock_radon(self):
        """本地提交前检查依赖与 CI 使用同一 radon 版本。"""

        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("radon==6.0.1", requirements)


if __name__ == "__main__":
    unittest.main()
