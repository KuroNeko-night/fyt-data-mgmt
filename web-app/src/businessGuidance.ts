/**
 * Web 业务的模板示意与工作流定义。
 *
 * 这里描述的是“帮助用户理解输入和输出”的轻量元数据，不读取真实业务文件，
 * 也不参与 Core 计算；业务算法仍由服务端和 `core/` 负责。模板字段使用实际业务
 * 常见列名，示例值只用于说明列的形状，避免用户把示例当成真实业务数据。
 */

export type TemplateGuide = {
  name: string;
  description: string;
  headers: string[];
  rows: string[][];
  output: string;
  tips: string[];
};

export type BusinessGuidance = {
  key: string;
  purpose: string;
  template: TemplateGuide;
};

export type DailyReportTabKey = "overview" | "attendance" | "workshop" | "production" | "brief";

export type WorkflowStep = {
  featureKey: string;
  title: string;
  description: string;
  input: string;
  /** 专用页面路由；缺省时按 featureKey 打开通用业务工作区。 */
  route?: "workshop" | "daily-report";
  /** route 为 daily-report 时打开的初始栏目。 */
  target?: DailyReportTabKey;
};

export type WorkflowDefinition = {
  key: string;
  title: string;
  description: string;
  audience: string;
  steps: WorkflowStep[];
};

const row = (...cells: string[]) => cells;

/** 每个业务的模板示意；不在此重复文件上传协议，协议仍以 FeatureWorkspace.SPECS 为准。 */
export const BUSINESS_GUIDANCE: Record<string, BusinessGuidance> = {
  attendance: { key: "attendance", purpose: "把打卡记录整理成可填报的考勤表。", template: { name: "打卡记录.xlsx", description: "每行一名员工在一天内的打卡信息。", headers: ["姓名", "日期", "上班打卡", "下班打卡"], rows: [row("张三", "2026-08-19", "08:02", "17:35"), row("李四", "2026-08-19", "08:10", "--")], output: "考勤填报表：出勤、工时、加班和异常说明。", tips: ["姓名应能与考勤模板中的人员匹配。", "缺少下班打卡会被标记为异常，不必手工补造时间。"] } },
  attendance_archive: { key: "attendance_archive", purpose: "把已填报的每日考勤汇总为月度统计。", template: { name: "考勤填报表.xlsx", description: "已经完成每日填报的考勤明细。", headers: ["姓名", "日期", "出勤状态", "实际工时"], rows: [row("张三", "2026-08-01", "出勤", "9"), row("张三", "2026-08-02", "休息", "0")], output: "考勤月度归档：出勤天数、工时、加班和异常。", tips: ["同一月份可同时选择多份每日填报表。", "系统会按姓名和日期合并，重复记录会提示。"] } },
  reconcile: { key: "reconcile", purpose: "核对目标工时、来源工时和劳务工时之间的差异。", template: { name: "工时对账资料.xlsx", description: "目标表、来源表和劳务表分别提供一组工时依据。", headers: ["姓名", "日期", "目标工时", "来源工时"], rows: [row("张三", "2026-08-19", "9", "8.5"), row("李四", "2026-08-19", "9", "9")], output: "工时对账报告：差异、匹配状态、来源说明和可信度。", tips: ["先扫描并确认人员/来源匹配，再执行最终对账。", "同名人员存在歧义时优先使用复核界面确认。"] } },
  arrival: { key: "arrival", purpose: "从成品送货计划识别到料、未到料和批次缺口。", template: { name: "每日主料到料明细.xlsx", description: "成品计划中包含批次、物料和计划/实收数量。", headers: ["批次号", "物料号", "物料描述", "计划数量", "实收数量"], rows: [row("260819-01", "MAT-001", "主料 A", "100", "100"), row("260819-01", "MAT-002", "主料 B", "80", "60")], output: "到料明细：到料率、批次进度，以及具体缺料和缺口数量。", tips: ["批次号和主料总类数优先从表内自动识别。", "剩余未收数非零的物料会自动列入未到料。"] } },
  pivot: { key: "pivot", purpose: "直接清洗采购来源并按物料属性聚合采购数量。", template: { name: "采购数据来源.xlsx", description: "来源表中提供物料编码、描述、规格、单位和最终采购数。", headers: ["物料号", "物料描述", "规格", "单位", "最终采购数"], rows: [row("MAT-001", "螺栓", "M8", "个", "120"), row("MAT-001", "螺栓", "M8", "个", "80")], output: "采购汇总：清洗明细子表、物料聚合主表和来源汇总自检。", tips: ["不要求输出原生 Excel 透视对象。", "系统会在最终采购数汇总前后做一致性校验。"] } },
  purchase: { key: "purchase", purpose: "逐行比对我方采购数和供应商采购数。", template: { name: "双方采购表.xlsx", description: "分别提供我方与供应商的采购明细。", headers: ["物料号", "物料描述", "我方数量", "供应商数量"], rows: [row("MAT-001", "螺栓", "120", "120"), row("MAT-002", "螺母", "90", "85")], output: "采购对账报告：一致项、差异数量和差异原因待核对项。", tips: ["两张表的物料号是最稳定的匹配键。", "名称或单位不同但物料号一致时会保留提示。"] } },
  shipping_review: { key: "shipping_review", purpose: "过滤作废 BOX 后，对比包装实际数与活动工作表总数。", template: { name: "包装日计划 + 活动工作表.xlsx", description: "包装计划提供实际包装数量，活动工作表提供 Part No 和总数。", headers: ["Part No", "Chinese name", "实际包装数量", "总数", "差异"], rows: [row("P-001", "产品 A", "100", "100", "0"), row("P-002", "产品 B", "80", "90", "-10")], output: "发运评审对比报告：包装汇总、活动总数、差异和自检结论。", tips: ["BOX 状态为“已作废”的记录不会参与汇总。", "活动工作表默认读取文件保存时的活动工作表。"] } },
  delivery: { key: "delivery", purpose: "把物料清单和供应商信息整理成送货计划。", template: { name: "物料清单 + 供应商清单.xlsx", description: "物料表提供需求，供应商表提供匹配关系。", headers: ["物料号", "物料描述", "需求数量", "供应商", "计划日期"], rows: [row("MAT-001", "螺栓", "120", "供应商 A", "2026-08-20"), row("MAT-002", "螺母", "90", "供应商 B", "2026-08-20")], output: "送货计划：按供应商、批次和日期整理的送货明细。", tips: ["供应商清单缺失时可以使用主数据库补全。", "订单类型会影响送货计划的分组方式。"] } },
  supplier_batch: { key: "supplier_batch", purpose: "按批次和供应商整理采购明细，并补充交付日期。", template: { name: "供应商批次清单.xlsx", description: "批次清单中包含批次号、供应商和物料明细。", headers: ["批次号", "供应商", "物料号", "数量", "交付日期"], rows: [row("260819-01", "供应商 A", "MAT-001", "120", "待确认"), row("260819-02", "供应商 B", "MAT-002", "90", "待确认")], output: "供应商批次表：按供应商拆分的采购与交付明细。", tips: ["先扫描批次，再填写或确认交付日期。", "历史供应商明细只用于补充当前清单缺失信息。"] } },
  purchase_plan: { key: "purchase_plan", purpose: "将辅料清单按批次填入采购计划模板。", template: { name: "采购计划模板 + 辅料清单.xlsx", description: "模板提供格式，辅料汇总表提供批次和采购数量。", headers: ["批次号", "物料号", "供应商代码", "采购数量", "预计到货日期"], rows: [row("260819-01", "AUX-001", "S001", "300", "2026-08-22"), row("260819-02", "AUX-002", "S002", "160", "2026-08-23")], output: "批次采购计划：保留模板已有的仓库、采购员和到货日期信息。", tips: ["模板与辅料清单建议使用同一批次口径。", "缺少供应商代码时会提示主数据补全。"] } },
  purchase_diff: { key: "purchase_diff", purpose: "提取辅料清单中计划数量与实收数量不一致的记录。", template: { name: "辅料清单汇总.xlsx", description: "表中同时存在计划数、实收数或差异字段。", headers: ["批次号", "物料号", "计划数量", "实收数量", "差异"], rows: [row("260819-01", "AUX-001", "300", "280", "-20"), row("260819-02", "AUX-002", "160", "160", "0")], output: "采购差异清单：只保留需要跟进的差异记录。", tips: ["差异为 0 的记录不会成为重点项。", "导出前可在结果预览中确认差异方向。"] } },
  reconcile_statement: { key: "reconcile_statement", purpose: "选择批次并生成供应商对账单。", template: { name: "供应商采购清单.xlsx", description: "一份或多份供应商采购清单，包含批次和供应商列。", headers: ["供应商", "批次号", "物料号", "数量", "单价"], rows: [row("供应商 A", "260819-01", "MAT-001", "120", "--"), row("供应商 B", "260819-02", "MAT-002", "90", "--")], output: "供应商对账单：按供应商和选定批次生成正式账单。", tips: ["先扫描，再勾选需要出账的批次。", "每次生成都会保留结果版本，方便重新下载。"] } },
  invoice: { key: "invoice", purpose: "扫描发票文件夹中的 PDF 并按月份整理台账。", template: { name: "发票资料文件夹", description: "选择包含同一月份多张供应商发票 PDF 的文件夹。", headers: ["发票号码", "供应商", "开票日期", "不含税金额", "价税合计"], rows: [row("INV-001", "供应商 A", "2026-08-18", "1000", "1130"), row("INV-002", "供应商 B", "2026-08-19", "800", "904")], output: "发票台账：发票号码、供应商、税额和月份汇总。", tips: ["上传前按月份归集文件夹更容易复核。", "识别不确定的发票会进入人工确认。"] } },
  invoice_match: { key: "invoice_match", purpose: "把发票台账与采购明细按供应商进行票货匹配。", template: { name: "发票台账 + 采购明细.xlsx", description: "发票台账提供开票数据，采购明细提供供应商采购数据。", headers: ["供应商", "发票含税金额", "采购金额", "匹配状态", "说明"], rows: [row("供应商 A", "1130", "1130", "匹配", ""), row("供应商 B", "904", "880", "需核对", "金额差异")], output: "票货匹配报告：正常、无票采购和有票无采购供应商。", tips: ["供应商名称不一致时优先维护主数据库映射。", "结果同时提供在线摘要和正式下载文件。"] } },
  rename: { key: "rename", purpose: "按规则批量生成文件的新名称。", template: { name: "待重命名文件", description: "选择上传到当前任务的文件副本。", headers: ["原文件名", "查找内容", "替换内容", "新文件名"], rows: [row("报告_旧.xlsx", "旧", "新", "报告_新.xlsx"), row("计划.xlsx", "", "", "计划.xlsx")], output: "重命名结果：新文件副本和冲突提示。", tips: ["只处理上传副本，不会改动本机原文件。", "执行前建议先检查预览出的冲突项。"] } },
  text: { key: "text", purpose: "对粘贴的文本进行去重、排序或内容提取。", template: { name: "文本输入", description: "把需要处理的多行文本粘贴到输入框。", headers: ["原始行", "处理方式", "结果行"], rows: [row("A", "去重", "A"), row("A", "去重", "（合并重复项）")], output: "文本处理结果：可复制的规范化文本。", tips: ["不同处理方式只影响文本，不会生成业务表格。", "保留默认方式即可快速得到可复制结果。"] } },
  pdf: { key: "pdf", purpose: "合并、拆分、提取或删除 PDF 页面。", template: { name: "PDF 文件", description: "根据处理方式选择一份或多份 PDF。", headers: ["文件", "模式", "页码范围", "输出"], rows: [row("资料 A.pdf", "合并", "全部", "合并文件.pdf"), row("资料 B.pdf", "合并", "全部", "合并文件.pdf")], output: "PDF 处理结果：按模式生成一个或多个 PDF 文件。", tips: ["合并模式可多选文件，其余模式默认处理第一份。", "页码范围使用 1-3、5 这样的格式。"] } },
  excel: { key: "excel", purpose: "合并、拆分、转换或纵向拼接表格。", template: { name: "Excel / CSV 文件", description: "可选择一个或多个结构相近的表格。", headers: ["文件", "工作表", "表头", "处理方式"], rows: [row("一月.xlsx", "Sheet1", "有", "纵向合并"), row("二月.xlsx", "Sheet1", "有", "纵向合并")], output: "表格处理结果：合并、拆分或转换后的文件。", tips: ["纵向合并前请确认列含义一致。", "公式是否保留由处理参数决定。"] } },
  compare: { key: "compare", purpose: "按关键列找出两张表的新增、缺失和差异记录。", template: { name: "A 表 + B 表", description: "A 表和 B 表提供同一批对象的两个版本。", headers: ["关键列", "A 表值", "B 表值", "差异类型"], rows: [row("MAT-001", "100", "100", "一致"), row("MAT-002", "80", "90", "数量差异")], output: "表格比对报告：一致项、差异项和无法匹配项。", tips: ["留空关键列时会自动寻找公共列。", "重复键会保留最少差异配对并提示复核。"] } },
  currency: { key: "currency", purpose: "把人民币数字转换为中文大写金额。", template: { name: "金额输入", description: "输入一个合法的人民币金额。", headers: ["数字金额", "中文大写"], rows: [row("12345.67", "壹万贰仟叁佰肆拾伍元陆角柒分"), row("0", "零元整")], output: "中文大写金额：可直接复制到合同、对账单或发票资料。", tips: ["只输入数字和小数点，不要输入货币符号。", "系统会拒绝 NaN、Infinity 等无效值。"] } },
};

/** 面向“顺着做”的业务路径；步骤键必须对应后端 FEATURE key 或专用页面路由。 */
export const WORKFLOW_DEFINITIONS: WorkflowDefinition[] = [
  { key: "daily-close", title: "今日业务闭环", description: "从当天资料整理开始，逐项确认到料、考勤、现场问题、安全与生产发运和重点事项。", audience: "适合管理员和日清资料维护人员", steps: [
    { featureKey: "arrival", title: "确认每日到料", description: "识别批次、主料总类和具体缺料。", input: "每日主料到料明细.xlsx" },
    { featureKey: "attendance", route: "daily-report", target: "attendance", title: "整理人员考勤", description: "在日清考勤栏目维护参会人员和生产班组出勤。", input: "参会名册 + 生产班组与班次" },
    { featureKey: "workshop", route: "workshop", title: "补充现场问题", description: "发布当天新增问题，并闭环已解决事项。", input: "现场问题规范字段" },
    { featureKey: "daily-production", route: "daily-report", target: "production", title: "上传安全与生产发运资料", description: "上传安全检查日报、生产计划、订单与发运表，自动进入当天总览。", input: "安全检查日报 + 生产与发运统计.xlsx" },
    { featureKey: "daily-brief", route: "daily-report", target: "brief", title: "维护事项与待办", description: "录入重大事项、通报、过程指标和会议待办。", input: "事项、指标与会议待办" },
    { featureKey: "daily-report", route: "daily-report", target: "overview", title: "查看日清看板总览", description: "核对到料、考勤、问题、安全与生产、事项是否完整。", input: "日清资料与生产数据" },
  ] },
  { key: "procurement", title: "采购到对账", description: "把采购来源整理成汇总，再生成批次和供应商对账资料。", audience: "适合采购和供应链人员", steps: [
    { featureKey: "pivot", title: "生成采购汇总", description: "清洗物料并按物料号聚合采购数量。", input: "采购数据来源.xlsx" },
    { featureKey: "purchase_plan", title: "导入采购计划", description: "将辅料清单填入采购计划模板。", input: "采购计划模板 + 辅料清单" },
    { featureKey: "supplier_batch", title: "整理供应商批次", description: "按供应商确认批次和交付日期。", input: "供应商批次清单.xlsx" },
    { featureKey: "reconcile_statement", title: "制作对账单", description: "勾选需要出账的批次并生成供应商对账单。", input: "供应商采购清单.xlsx" },
  ] },
  { key: "delivery", title: "送货与到料", description: "先生成送货计划，再用成品表核对实际到料和缺口。", audience: "适合计划和物料人员", steps: [
    { featureKey: "delivery", title: "生成送货计划", description: "匹配物料、供应商和计划日期。", input: "物料清单 + 供应商清单" },
    { featureKey: "arrival", title: "处理每日到料", description: "查看批次进度和未到物料缺口。", input: "每日主料到料明细.xlsx" },
    { featureKey: "shipping_review", title: "核对发运评审", description: "过滤作废 BOX 并比较包装数量。", input: "包装日计划 + 活动工作表" },
  ] },
  { key: "finance", title: "财务票货核对", description: "先识别发票，再与采购明细比对供应商票货关系。", audience: "适合财务人员", steps: [
    { featureKey: "invoice", title: "生成发票台账", description: "扫描发票文件夹中的 PDF 并汇总。", input: "发票资料文件夹" },
    { featureKey: "invoice_match", title: "进行票货匹配", description: "比对发票台账与采购明细。", input: "发票台账 + 采购明细" },
    { featureKey: "purchase", title: "复核采购差异", description: "需要时再对照双方采购表确认数量差异。", input: "双方采购表.xlsx" },
  ] },
];

export function guidanceFor(key: string, title = "业务模板"): BusinessGuidance {
  return BUSINESS_GUIDANCE[key] || {
    key,
    purpose: "按照当前业务页面的输入项完成处理。",
    template: { name: `${title}输入示意`, description: "以下仅用于说明字段形状，实际列名以业务模板为准。", headers: ["输入字段", "处理参数", "输出结果"], rows: [row("文件或文本", "默认设置", "结构化结果")], output: "处理完成后可在线查看结果，并下载正式文件。", tips: ["不确定时先使用页面给出的默认参数。"] },
  };
}
