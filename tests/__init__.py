# -*- coding: utf-8 -*-
"""峰运通数据管理系统 —— 测试包。

覆盖两类测试：
  · 纯函数单元测试（common/currency/text/rename/pdf/paths），不碰磁盘或样本；
  · 集成测试（test_integration），用仓库自带的样本数据跑各功能 run()，
    输出写到临时目录，断言产物与关键指标。样本缺失时自动跳过。
"""
