# -*- coding: utf-8 -*-
"""峰运通数据管理系统 —— 核心业务逻辑包（与界面解耦）。

核心业务统一入口：
  · attendance_core.run —— 考勤数据填报
  · reconcile_core.run  —— 工时对账
  · arrival_core.run    —— 到料明细表
  · pivot_core.run      —— 销售表透视
  · purchase_core.run   —— 采购数对账
  · delivery_core.run   —— 送货计划表

公共设施：common_core（解析/选项）、paths（统一输出）、
settings（全局配置）、version（版本）、updater（更新检查）。
"""
