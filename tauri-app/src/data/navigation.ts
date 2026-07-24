export interface NavItem {
  key: string;
  group: string;
  title: string;
  description: string;
  icon: string;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "home", group: "", title: "首页", description: "业务工作台总览", icon: "home" },
  { key: "attendance", group: "人事", title: "考勤数据填报", description: "打卡数据自动填表并计算工时", icon: "calendar" },
  { key: "reconcile", group: "人事", title: "工时对账", description: "多方工时核对与异常汇总", icon: "check" },
  { key: "arrival", group: "销售", title: "到料明细表", description: "扫描送货计划并统计未收料", icon: "truck" },
  { key: "pivot", group: "销售", title: "销售表透视", description: "采购数据清洗、汇总与可信度报告", icon: "chart" },
  { key: "purchase", group: "销售", title: "采购数对账", description: "我方与供应商采购数量逐行比对", icon: "compare" },
  { key: "delivery", group: "销售", title: "送货计划表", description: "物料与供应商匹配生成送货计划", icon: "route" },
  { key: "library", group: "数据", title: "数据库", description: "表格自动识别、归档与复用", icon: "database" },
  { key: "tasks", group: "数据", title: "任务中心", description: "处理历史、耗时与结果位置", icon: "tasks" },
  { key: "mappings", group: "数据", title: "字段映射中心", description: "管理人工确认的字段映射", icon: "mapping" },
  { key: "templates", group: "数据", title: "模板中心", description: "模板版本、差异和迁移规则", icon: "template" },
  { key: "invoice", group: "财务", title: "增值税发票统计", description: "递归识别专票并生成月度台账", icon: "invoice" },
  { key: "currency", group: "财务", title: "金额大写", description: "人民币金额转换为中文大写", icon: "currency" },
  { key: "rename", group: "工具", title: "批量重命名", description: "规则化改名、预览与撤销", icon: "rename" },
  { key: "text", group: "工具", title: "文本工具箱", description: "去重、排序和内容提取", icon: "text" },
  { key: "pdf", group: "工具", title: "PDF 工具箱", description: "合并、拆分、提取和删页", icon: "pdf" },
  { key: "excel", group: "工具", title: "Excel 工具箱", description: "表格合并、拆分和格式转换", icon: "excel" },
  { key: "compare", group: "工具", title: "表格比对", description: "按关键列定位新增、删除和差异", icon: "compare" },
  { key: "settings", group: "系统", title: "设置", description: "外观、输出与运行偏好", icon: "settings" },
  { key: "about", group: "系统", title: "关于", description: "版本、运行环境与更新信息", icon: "about" },
];

export const HOME_SHORTCUTS = NAV_ITEMS.filter((item) =>
  ["attendance", "reconcile", "arrival", "pivot", "purchase", "delivery", "library", "invoice", "currency"].includes(item.key),
);
