# -*- coding: utf-8 -*-
"""
panel_widgets —— 右侧面板承载的内容部件
=======================================
把原先"单开子窗口"(QDialog)的正文抽成纯 QWidget，发信号代替 accept/reject，
由 MainWindow.open_panel 嵌进右侧可调面板显示，不再打断用户操作。
"""
