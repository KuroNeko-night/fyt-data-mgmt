# -*- coding: utf-8 -*-
"""右侧面板 RightPanel 多分区/折叠 API 的单元测试(offscreen)。

钉死:add_section 新增与同 key 替换、remove_section 清理、折叠改变高度分配、
关闭分区发 section_closed、全空发 closed、旧 set_content/clear_content 兼容。
"""
import os
import unittest
import warnings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings("ignore")

from PySide2.QtWidgets import QApplication, QLabel

from ui.widgets.side_panel import RightPanel

_app = QApplication.instance() or QApplication([])


class TestSections(unittest.TestCase):
    def setUp(self):
        self.p = RightPanel()

    def test_add_and_keys(self):
        self.p.add_section("a", "甲", QLabel("A"))
        self.p.add_section("b", "乙", QLabel("B"))
        self.assertEqual(self.p.section_keys(), ["a", "b"])
        self.assertTrue(self.p.has_sections())

    def test_same_key_replaces(self):
        self.p.add_section("a", "甲", QLabel("A"))
        w2 = QLabel("A2")
        sec = self.p.add_section("a", "甲改", w2)
        self.assertEqual(self.p.section_keys(), ["a"])   # 不新增
        self.assertEqual(sec.key(), "a")

    def test_remove(self):
        self.p.add_section("a", "甲", QLabel("A"))
        self.p.add_section("b", "乙", QLabel("B"))
        self.p.remove_section("a")
        self.assertEqual(self.p.section_keys(), ["b"])
        self.p.remove_section("b")
        self.assertFalse(self.p.has_sections())

    def test_close_signal(self):
        got = []
        self.p.section_closed.connect(got.append)
        emptied = []
        self.p.closed.connect(lambda: emptied.append(True))
        sec = self.p.add_section("a", "甲", QLabel("A"), closable=True)
        sec._on_close = None
        # 模拟关闭钮
        sec.closed.emit("a")
        self.assertEqual(got, ["a"])
        self.assertEqual(emptied, [True])           # 全空 -> closed

    def test_collapse_changes_height_budget(self):
        self.p.resize(300, 600)
        a = self.p.add_section("a", "甲", QLabel("A"))
        b = self.p.add_section("b", "乙", QLabel("B"))
        a.toggle()                                   # 折叠 a
        self.assertTrue(a.is_collapsed())
        sizes = self.p._splitter.sizes()
        # 折叠分区高度应明显小于展开分区
        self.assertLess(sizes[0], sizes[1])

    def test_legacy_set_clear(self):
        self.p.set_content(QLabel("X"), "标题")
        self.assertEqual(self.p.section_keys(), ["main"])
        self.p.clear_content()
        self.assertFalse(self.p.has_sections())

    def test_non_closable_has_no_close_button(self):
        from PySide2.QtWidgets import QPushButton
        sec = self.p.add_section("preview", "文件预览", QLabel("P"), closable=False)
        btns = [b for b in sec.findChildren(QPushButton)
                if b.objectName() == "PanelClose"]
        self.assertEqual(btns, [])                   # 不可关闭分区无 ✕
        # 折叠钮仍在(可折叠但不可叉)
        folds = [b for b in sec.findChildren(QPushButton)
                 if b.objectName() == "PanelFold"]
        self.assertEqual(len(folds), 1)


class TestPreviewReopen(unittest.TestCase):
    """钉死已修复的崩溃:预览分区叉掉后无法再开(悬垂 C++ 对象 RuntimeError)。

    预览分区改为不可关闭(只随面板隐藏/显示);移除后再预览须重建、不得崩。"""
    def setUp(self):
        import tempfile, openpyxl
        from ui.main_window import MainWindow
        self.w = MainWindow()
        self.tmp = tempfile.mkdtemp(prefix="fyt_prev_")
        self.p1 = os.path.join(self.tmp, "a.xlsx")
        self.p2 = os.path.join(self.tmp, "b.xlsx")
        for path, code in ((self.p1, "A1"), (self.p2, "B1")):
            wb = openpyxl.Workbook(); ws = wb.active
            ws.append(["物料号", "名称"]); ws.append([code, "x"]); wb.save(path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preview_section_not_closable(self):
        from PySide2.QtWidgets import QPushButton
        self.w.preview_file(self.p1)
        sec = self.w._right_panel._sections["preview"]
        closes = [b for b in sec.findChildren(QPushButton)
                  if b.objectName() == "PanelClose"]
        self.assertEqual(closes, [])                 # 预览分区无关闭钮

    def test_remove_then_preview_again(self):
        from ui.main_window import _qt_alive
        self.w.preview_file(self.p1)
        self.w.preview_file(None)                    # 移除预览分区
        self.assertNotIn("preview", self.w._right_panel.section_keys())
        self.assertIsNone(self.w._preview_widget)    # 悬垂引用已清
        # 侧栏不因此收起,占位仍在;再预览应重建成功(旧代码此处 RuntimeError)
        self.w.preview_file(self.p2)
        self.assertIn("preview", self.w._right_panel.section_keys())
        self.assertTrue(_qt_alive(self.w._preview_widget))


class TestPanelDefaultOpen(unittest.TestCase):
    """钉死:侧栏默认展开(无内容显示占位);点"人工核对"即便之前手动隐藏也强制展开;
    折叠标题条固定高不错位。"""
    def _pump(self, ms=300):
        import time
        end = time.time() + ms / 1000.0
        while time.time() < end:
            _app.processEvents(); time.sleep(0.01)

    def setUp(self):
        from ui.main_window import MainWindow
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        self._pump(400)

    def test_visible_by_default_empty(self):
        self.assertTrue(self.w._right_panel.isVisible())
        self.assertFalse(self.w._panel_hidden)
        self.assertEqual(self.w._right_panel.section_keys(), [])   # 空占位

    def test_open_panel_forces_open_after_hide(self):
        self.w.toggle_panel(); self._pump()          # 用户手动隐藏
        self.assertTrue(self.w._panel_hidden)
        self.w.open_panel(QLabel("复核"), "人工核对", key="review")
        self._pump()
        self.assertFalse(self.w._panel_hidden)        # 明确意图 -> 解除隐藏
        self.assertTrue(self.w._right_panel.isVisible())
        self.assertIn("review", self.w._right_panel.section_keys())

    def test_close_section_keeps_panel_visible(self):
        self.w.open_panel(QLabel("复核"), "人工核对", key="review"); self._pump()
        self.w.close_panel("review"); self._pump()
        self.assertEqual(self.w._right_panel.section_keys(), [])
        self.assertTrue(self.w._right_panel.isVisible())   # 不收起,留占位

    def test_collapsed_header_fixed_height(self):
        self.w.open_panel(QLabel("复核"), "人工核对", key="review"); self._pump()
        sec = self.w._right_panel._sections["review"]
        self.assertEqual(sec.header_height(), sec.HEADER_H)
        sec.toggle(); self._pump()
        self.assertTrue(sec.is_collapsed())
        self.assertEqual(sec.maximumHeight(), sec.HEADER_H)   # 折叠恰好=标题条高,不裁切


if __name__ == "__main__":
    unittest.main()
