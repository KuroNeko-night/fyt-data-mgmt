# -*- coding: utf-8 -*-
"""
首页 —— 品牌门面 + 快捷入口 + 数据库概览 + 完整帮助文档
======================================================
程序启动后的落地页。让用户一眼看懂能做什么、数据在哪、怎么用。
兼容 Windows 7 + Python 3.8 + PySide2。
"""
import os

from PySide2.QtCore import Qt
from PySide2.QtGui import QPixmap
from PySide2.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QFrame, QPushButton)

from .base_page import BasePage
from ..widgets.clickable_card import ClickableCard
from core import version, library, paths

ENTRIES = [
    ("attendance", "attendance", "考勤数据填报", "打卡系统数据 → 自动填入待填考勤表并算工时"),
    ("reconcile", "reconcile", "工时对账", "来源与对账单核对，出异常汇总 + 可信度评分"),
    ("arrival", "arrival", "到料明细表", "扫描送货计划，统计未收料，生成每日到料明细"),
    ("pivot", "pivot", "销售表透视", "采购数据自动清洗汇总，生成原生数据透视表"),
    ("purchase", "purchase", "采购数对账", "我方对账单与供应商对单逐行比对，出差异报告"),
    ("delivery", "delivery", "送货计划表", "物料清单配供应商，一键生成送货计划底表"),
    ("library", "library", "数据库", "把各处表格拖进来，自动识别归档、随取随用"),
    ("invoice", "invoice", "增值税发票统计", "扫描资料文件夹，自动识别专用发票并汇总成月度台账"),
    ("currency", "currency", "金额大写", "数字金额一键转中文大写，开票报销可直接用"),
    ("rename", "rename", "批量重命名", "按规则批量改名，实时预览、可撤销"),
    ("text", "text", "文本工具箱", "去重、排序、去空行、提取邮箱手机号等"),
    ("pdf", "pdf", "PDF 工具箱", "合并、拆分、提取或删除 PDF 指定页"),
    ("excel", "excel", "Excel 工具箱", "多簿合并、按表拆分、格式转换、纵向合并"),
]


class HomePage(BasePage):
    def __init__(self, main):
        super(HomePage, self).__init__(
            main, "欢迎使用",
            "峰运通数据管理系统 —— 六大核心业务一站式处理，数据自动归档。")

    def build_body(self, layout):
        layout.addWidget(self._hero())
        sec = QLabel("快捷入口"); sec.setObjectName("SecTitle")
        layout.addWidget(sec)
        grid = QGridLayout(); grid.setSpacing(12)
        self._cards = []
        for i, (key, icon_name, title, desc) in enumerate(ENTRIES):
            card = ClickableCard(key, icon_name, title, desc)
            card.clicked.connect(self.main.switch_to)
            grid.addWidget(card, i // 3, i % 3)
            self._cards.append(card)
        layout.addLayout(grid)

        self.stats = QLabel(""); self.stats.setObjectName("Hint")
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)

        layout.addWidget(self._help())
        layout.addStretch(1)
        self.refresh_view()

    def _hero(self):
        card = QFrame(); card.setObjectName("HeroCard")
        h = QHBoxLayout(card); h.setContentsMargins(24, 22, 24, 22); h.setSpacing(20)
        logo = QLabel()
        p = os.path.join(paths.assets_dir(), "logo_128.png")
        if os.path.exists(p):
            logo.setPixmap(QPixmap(p).scaled(84, 84, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
        h.addWidget(logo, 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(5)
        top = QHBoxLayout(); top.setSpacing(10)
        name = QLabel(version.APP_NAME); name.setObjectName("HeroTitle")
        top.addWidget(name, 0, Qt.AlignVCenter)
        ver = QLabel("v" + version.version_str()); ver.setObjectName("HeroPill")
        ver.setAlignment(Qt.AlignCenter)
        top.addWidget(ver, 0, Qt.AlignVCenter)
        top.addStretch(1)
        col.addLayout(top)
        rule = QFrame(); rule.setObjectName("HeroRule"); rule.setFixedHeight(3)
        rule.setFixedWidth(46)
        col.addWidget(rule)
        intro = QLabel("面向峰运通业务打造：考勤填报、工时对账、到料明细、透视表、"
                       "采购对账、送货计划六大核心业务，另配实用工具箱；"
                       "输出统一归档，自带数据库自动分类管理各类表格。")
        intro.setObjectName("HeroDesc"); intro.setWordWrap(True)
        col.addWidget(intro)
        h.addLayout(col, 1)
        return card

    def _help(self):
        from ..widgets.collapsible import Collapsible
        box = QFrame(); box.setObjectName("Card")
        v = QVBoxLayout(box); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        title = QLabel("使用帮助"); title.setObjectName("SecTitle")
        v.addWidget(title)
        for i, (t, html) in enumerate(_HELP):
            v.addWidget(Collapsible(t, html, expanded=(i == 0)))
        return box

    def on_theme_changed(self):
        super(HomePage, self).on_theme_changed()
        for card in getattr(self, "_cards", []):
            card.refresh_icon()

    def refresh_view(self):
        c = library.counts()
        total = sum(c.get(k, 0) for k in (library.CATEGORIES + [library.UNKNOWN]))
        if not total:
            self.stats.setText("数据库当前为空 —— 到「数据库」页把常用表拖进来，"
                               "各功能就能自动取用。")
            return
        parts = []
        for cat in library.CATEGORIES:
            if c.get(cat):
                parts.append("%s %d" % (library.CATEGORY_TITLES[cat], c[cat]))
        line = "数据库已归档 %d 张表：" % total + "　".join(parts)
        if c.get(library.UNKNOWN):
            line += "　·　未识别 %d" % c[library.UNKNOWN]
        self.stats.setText(line)


_HELP = [
    ("整体流程 · 数据存到哪",
     "本系统各功能的<b>输出统一归档</b>在：<br>"
     "&nbsp;&nbsp;<code>文档 / 峰运通数据管理系统 / 输出 / &lt;功能名&gt; / &lt;时间戳&gt;</code><br>"
     "输入来源不限；建议先把常用表拖进<b>「数据库」</b>，程序会自动识别用途归档，"
     "之后在各功能页点<b>“从数据库选择 / 载入最新”</b>即可直接取用，不必每次到处找文件。"),
    ("① 考勤数据填报",
     "<b>需要：</b>系统数据（打卡来源，可多选）+ 待填考勤表（目标，可多选）。<br>"
     "<b>做什么：</b>按“姓名 + 日期”把打卡时间填入考勤表，算出实际工时。<br>"
     "<b>输出：</b>每个考勤表另存为“_已填写”，可一键送去「工时对账」。"),
    ("② 工时对账",
     "<b>需要：</b>待对总表（单个）+ 数据来源（工时明细，可多选）+ 对账单（劳务方，可多选）。<br>"
     "<b>做什么：</b>把来源工时填入总表并与对账单逐项核对。<br>"
     "<b>输出：</b>填好的总表 + 异常汇总表 + <b>可信度评分</b>（可信 / 需复核 / 存疑）。"),
    ("③ 到料明细表",
     "<b>需要：</b>送货计划表（含“剩余未收”列，可多选）。<br>"
     "<b>做什么：</b>识别批次、统计未收料物料，可手改主料总类数与备注。<br>"
     "<b>输出：</b>每日主料到料明细表（样式与示例一致）。"),
    ("④ 销售表透视",
     "<b>需要：</b>采购数据表（包装方案 / PFEP / 采购量核算 / 组托辅材，可多选）。<br>"
     "<b>做什么：</b>自动定位表头、清洗数据、统一单位规格，按编码/名称/规格/单位分组汇总。<br>"
     "<b>输出：</b>Excel 原生数据透视表 + 分组合计 + 可信度报告。“人工复核后生成…”可先核对再出表。"),
    ("⑤ 采购数对账",
     "<b>需要：</b>我方对账单（单个）+ 供应商对单明细（单个）。<br>"
     "<b>做什么：</b>按物料/批次逐行比对两方采购数量，标出差异。<br>"
     "<b>输出：</b>我方对账单数量列上色 + 差异汇报表。"),
    ("⑥ 送货计划表",
     "<b>需要：</b>物料清单（单个）+ 供应商明细（单个），两份顺序随意、程序自动辨识。<br>"
     "<b>做什么：</b>以物料清单为主，按物料号带出供应商代码与名称。<br>"
     "<b>输出：</b>送货计划底表（到货/收货等跟单列留空，供后续填写）。"),
    ("🗄 数据库怎么用",
     "把任意表格<b>拖进「数据库」页</b>，程序据文件名与表头自动判定它属于哪一类"
     "（填报系统数据 / 待填考勤表 / 对账来源 / 待对总表 / 劳务对账单 / 采购数据 / "
     "送货计划 / 采购对账单 / 物料清单 / 供应商明细），"
     "复制归档并记录最后更新日期与可信度；<b>没识别出来的会单独进“未识别”</b>，可手动“重新分类”。<br>"
     "导入后会询问是否删除原文件——删不删都不影响库里的副本。同一张表更新后再导入会<b>自动替换旧版</b>。"),
    ("💴 增值税发票统计",
     "<b>需要：</b>一个资料文件夹（含发票 PDF，程序会<b>递归</b>扫描所有子文件夹）。<br>"
     "<b>做什么：</b>自动挑出<b>增值税专用发票</b>，抽取号码/日期/销售方/金额/税率，"
     "按月份汇总；生成前弹<b>人工复核</b>，可逐张核对、改费用项目与备注、排除某张票。<br>"
     "<b>输出：</b>月度汇总台账 + 一个<b>专用发票复核文件夹</b>（原始 PDF 按月归档，"
     "另附<b>存疑清单</b>列出没能确认的文件，供人工二次核对，避免漏收）。"),
    ("常见问题",
     "<b>· 提示“文件被占用”？</b>先关掉正在用 Excel 打开的那张表再运行。<br>"
     "<b>· 结果找不到？</b>运行完会自动打开输出文件夹；也可点各页“打开输出文件夹”。<br>"
     "<b>· 识别错了？</b>透视/对账页支持“人工复核”；数据库里可“重新分类”。<br>"
     "<b>· 支持 .xls 吗？</b>支持 .xlsx / .xlsm / .xls。<br>"
     "<b>· 深色模式？</b>「设置 · 外观」可选 跟随系统 / 浅色 / 深色。"),
]
