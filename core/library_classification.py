"""文件库的可扩展分类评分规则。

每个业务类别使用一个独立评分函数，统一通过 :class:`ClassificationContext` 读取文件名、
页签表头和扩展名。规则返回的分数是启发式权重而非概率；调用方仍负责跨页签比较、阈值
判断和多标签选择。新增业务模块时只需新增评分函数并注册到 ``SCORERS``。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


Score = tuple[int, list[str]]
Scorer = Callable[["ClassificationContext"], Score]


def normalize_keyword_text(value: object) -> str:
    """移除空白，生成只用于文件名和表头关键词匹配的文本。"""
    return re.sub(r"\s+", "", str(value)) if value is not None else ""


@dataclass(frozen=True)
class ClassificationContext:
    """单个页签评分所需的只读输入。"""

    file_name: str
    tokens: frozenset[str]
    extension: str

    @classmethod
    def build(
        cls,
        file_name: str,
        tokens: Iterable[str],
        extension: str,
    ) -> "ClassificationContext":
        """规范化文件名和表头集合，避免每条规则重复清洗文本。"""
        return cls(
            file_name=normalize_keyword_text(file_name),
            tokens=frozenset(tokens),
            extension=extension.lower(),
        )

    def has(self, *needles: str) -> bool:
        """判断任一表头文本是否包含任一候选关键词。"""
        return any(needle in token for token in self.tokens for needle in needles)

    def file_name_has(self, *needles: str) -> bool:
        """判断规范化文件名是否包含任一候选关键词。"""
        return any(needle in self.file_name for needle in needles)


@dataclass
class ScoreBuilder:
    """累加分数和可解释信号，避免规则里反复维护并行变量。"""

    score: int = 0
    signals: list[str] = field(default_factory=list)

    def add(self, points: int, signal: str | None = None) -> None:
        """条件已满足时增加权重，并可记录面向管理员的命中原因。"""
        self.score += points
        if signal:
            self.signals.append(signal)

    def result(self) -> Score:
        """返回与现有分类接口兼容的 ``(分数, 信号)``。"""
        return self.score, self.signals


def _score_attendance_source(ctx: ClassificationContext) -> Score:
    """识别考勤系统导出的原始打卡数据。"""
    result = ScoreBuilder()
    if ctx.has("上班1打卡"):
        result.add(70, "含“上班1打卡”列")
    if ctx.has("姓名"):
        result.add(12, "含“姓名”")
    if ctx.file_name_has("打卡", "考勤机", "每日统计", "系统导出"):
        result.add(15, "文件名含打卡/统计")
    return result.result()


def _score_attendance_target(ctx: ClassificationContext) -> Score:
    """识别需要程序回填的考勤表。"""
    result = ScoreBuilder()
    if ctx.has("上班1打卡"):
        return result.result()
    if ctx.has("休息时间"):
        result.add(42, "含“休息时间”列")
    if ctx.has("实际工作时间", "实际工时"):
        result.add(22, "含“实际工作时间”")
    if ctx.has("上班时间", "下班时间"):
        result.add(16, "含上/下班时间列")
    if ctx.has("姓名") and ctx.has("日期"):
        result.add(12, "含姓名+日期")
    if ctx.file_name_has("考勤表", "待填", "考勤"):
        result.add(12, "文件名含考勤表")
    return result.result()


def _score_reconcile_source(ctx: ClassificationContext) -> Score:
    """识别对账使用的我方工时明细。"""
    result = ScoreBuilder()
    excluded = (
        ctx.has("上班1打卡")
        or ctx.has("休息时间")
        or ctx.has("所属劳务公司")
        or ctx.file_name_has("对账单", "劳务", "结算")
    )
    if excluded:
        return result.result()
    if ctx.has("实际工作时间", "实际工时"):
        result.add(46, "含“实际工作时间”明细")
    if ctx.has("姓名") and ctx.has("日期"):
        result.add(22, "含姓名+日期")
    if ctx.file_name_has("明细", "工时", "已填写"):
        result.add(10, "文件名含明细/工时")
    return result.result()


def _score_reconcile_summary(ctx: ClassificationContext) -> Score:
    """识别劳务对账的待对总表。"""
    result = ScoreBuilder()
    if ctx.has("所属劳务公司"):
        result.add(55, "含“所属劳务公司”")
    if ctx.has("出勤工时"):
        result.add(30, "含“出勤工时”")
    if ctx.has("对账时间"):
        result.add(28, "含“对账时间”")
    if result.score and ctx.has("姓名"):
        result.add(10)
    if ctx.file_name_has("总表", "待对"):
        result.add(10, "文件名含总表/待对")
    return result.result()


def _score_labor_statement(ctx: ClassificationContext) -> Score:
    """识别格式差异较大的劳务对账单。"""
    result = ScoreBuilder()
    if ctx.file_name_has("劳务", "对账单", "工时单", "结算"):
        result.add(42, "文件名含劳务/对账单")
    if ctx.has("姓名"):
        result.add(18, "含“姓名”")
    if ctx.has("合计", "小计"):
        result.add(14, "含合计列")
    if ctx.extension == ".xls":
        result.add(8)
    return result.result()


def _score_pivot_source(ctx: ClassificationContext) -> Score:
    """识别采购量核算与透视汇总的数据源。"""
    result = ScoreBuilder()
    if ctx.has("最终采购数量"):
        result.add(45, "含“最终采购数量”")
    if ctx.has("材料编号", "物料编号", "物料号", "料号", "物料编码"):
        result.add(30, "含材料/物料编号")
    if ctx.file_name_has("采购量核算", "pfep", "包装方案", "组托辅材", "包材用量", "组托"):
        result.add(35, "文件名含采购/PFEP/组托")
    if ctx.has("规格") and ctx.has("单位"):
        result.add(10, "含规格+单位")
    return result.result()


def _score_arrival_plan(ctx: ClassificationContext) -> Score:
    """识别每日到料使用的送货计划。"""
    result = ScoreBuilder()
    if ctx.file_name_has("送货计划"):
        result.add(55, "文件名含“送货计划”")
    if ctx.has("剩余未收", "未收数", "未收货", "未收料"):
        result.add(30, "含未收料列")
    if ctx.has("供应商"):
        result.add(14, "含“供应商”")
    if ctx.has("编码", "物料编码", "物料编号"):
        result.add(10)
    return result.result()


def _score_purchase_statement(ctx: ClassificationContext) -> Score:
    """识别采购数量对账单，并排除采购透视源和劳务表。"""
    result = ScoreBuilder()
    matches = (
        ctx.has("批次号")
        and ctx.has("采购数量")
        and not ctx.has("最终采购数量")
        and not ctx.has("姓名")
        and not ctx.has("实际工时", "出勤工时")
    )
    if not matches:
        return result.result()
    result.add(55, "含批次号+采购数量")
    if ctx.has("材料编号", "物料编号", "材料号", "物料号"):
        result.add(25, "含材料编号")
    if ctx.has("材料名称", "物料名称"):
        result.add(10, "含材料名称")
    if ctx.file_name_has("对账单", "对单", "结算单"):
        result.add(12, "文件名含对账/对单")
    return result.result()


def _score_delivery_bom(ctx: ClassificationContext) -> Score:
    """识别包含中英文描述的 KD/SUB 物料清单。"""
    result = ScoreBuilder()
    if not ctx.has("物料中文描述", "物料英文描述", "中文描述", "英文描述"):
        return result.result()
    result.add(55, "含物料中/英文描述")
    if ctx.has("物料号", "物料编码") and ctx.has("数量"):
        result.add(25, "含物料号+数量")
    if ctx.file_name_has("物料清单", "bom", "kd", "sub"):
        result.add(12, "文件名含物料清单/KD")
    return result.result()


def _score_delivery_supplier(ctx: ClassificationContext) -> Score:
    """识别经典零部件表和 SAP KD 供应商明细。"""
    result = ScoreBuilder()
    if ctx.has("零部件代码"):
        result.add(50, "含零部件代码")
        if ctx.has("供应商代码", "供应商名称", "供应商"):
            result.add(25, "含供应商代码/名称")
        if ctx.has("库区", "结算方式", "属性", "订单情况"):
            result.add(12, "含库区/结算/属性列")
        return result.result()
    is_supplier_sheet = (
        ctx.has("供应商代码")
        and ctx.has("供应商名称")
        and not ctx.has("姓名")
        and not ctx.file_name_has("送货计划")
    )
    if not is_supplier_sheet:
        return result.result()
    result.add(55, "含供应商代码+供应商名称双列")
    if ctx.has("下阶物料", "下阶物料描述", "物料", "料号"):
        result.add(12, "含物料/下阶物料列")
    if ctx.has("库区", "结算方式", "科室", "订单情况", "发货数量", "签收数量", "批次号"):
        result.add(12, "含库区/结算/发签数等供应商表列")
    return result.result()


SCORERS: tuple[tuple[str, Scorer], ...] = (
    ("att_source", _score_attendance_source),
    ("att_target", _score_attendance_target),
    ("rec_source", _score_reconcile_source),
    ("rec_zong", _score_reconcile_summary),
    ("rec_labor", _score_labor_statement),
    ("pivot_src", _score_pivot_source),
    ("arrival_plan", _score_arrival_plan),
    ("purchase_stmt", _score_purchase_statement),
    ("deliv_bom", _score_delivery_bom),
    ("deliv_supp", _score_delivery_supplier),
)


def score_sheet(file_name: str, tokens: Iterable[str], extension: str) -> dict[str, Score]:
    """按注册顺序计算单个页签的全部业务分类分数。"""
    context = ClassificationContext.build(file_name, tokens, extension)
    return {category: scorer(context) for category, scorer in SCORERS}
