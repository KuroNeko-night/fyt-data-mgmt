/**
 * Tauri 桌面端导航的单一配置表。
 *
 * `key` 同时用于页面路由、快捷入口和页面元数据查找；新增桌面功能时应在此注册，
 * 不要在侧栏或工作台分别维护重复清单。分组为空的首页由侧栏固定置顶。
 */
export interface NavItem {
  key: string;
  group: string;
  title: string;
  description: string;
  icon: string;
}

// 数组顺序就是侧栏展示顺序，组内项目不再做额外排序。
export const NAV_ITEMS: NavItem[] = [
  { key: "home", group: "", title: "首页", description: "业务工作台总览", icon: "home" },
  { key: "attendance", group: "人事", title: "考勤数据填报", description: "上传打卡记录，自动生成考勤填报表", icon: "calendar" },
  { key: "attendance_archive", group: "人事", title: "考勤月度归档", description: "上传考勤填报表，汇总月度出勤统计", icon: "chart" },
  { key: "reconcile", group: "人事", title: "工时对账", description: "上传工时表，核对多方差异并汇总", icon: "check" },
  { key: "arrival", group: "销售", title: "到料明细表", description: "上传送货计划，统计到料与未收料", icon: "truck" },
  { key: "pivot", group: "销售", title: "销售表透视", description: "上传采购明细，汇总成透视表", icon: "chart" },
  { key: "purchase", group: "销售", title: "采购数对账", description: "上传双方采购表，逐行比对数量差异", icon: "compare" },
  { key: "delivery", group: "销售", title: "送货计划表", description: "上传物料与供应商清单，生成送货计划", icon: "route" },
  { key: "supplier_batch", group: "销售", title: "供应商批次表", description: "上传批次清单，按供应商生成采购明细", icon: "excel" },
  { key: "purchase_plan", group: "销售", title: "采购计划导入", description: "上传辅料清单与模板，生成批次采购计划", icon: "route" },
  { key: "reconcile_statement", group: "销售", title: "对账单制作", description: "选择批次，自动生成供应商对账单", icon: "doc" },
  { key: "library", group: "数据", title: "数据库", description: "表格自动归档，随时搜索复用", icon: "database" },
  { key: "tasks", group: "数据", title: "任务中心", description: "查看处理历史与结果文件", icon: "tasks" },
  { key: "mappings", group: "数据", title: "字段映射中心", description: "调整自动识别的字段对应关系", icon: "mapping" },
  { key: "catalog", group: "数据", title: "主数据档案", description: "维护供应商代码与材料档案", icon: "database" },
  { key: "batch_track", group: "数据", title: "批次跟踪", description: "按批次号查看全流程处理记录", icon: "search" },
  { key: "report_center", group: "数据", title: "报表中心", description: "按时间范围生成业务汇总报表", icon: "pie" },
  { key: "templates", group: "数据", title: "模板中心", description: "管理文件模板与版本", icon: "template" },
  { key: "invoice", group: "财务", title: "增值税发票统计", description: "上传 PDF 发票，自动识别并按月汇总", icon: "invoice" },
  { key: "currency", group: "财务", title: "金额大写", description: "输入金额，一键转中文大写", icon: "currency" },
  { key: "rename", group: "工具", title: "批量重命名", description: "选择文件，按规则批量改名", icon: "rename" },
  { key: "text", group: "工具", title: "文本工具箱", description: "粘贴文本，去重、排序或提取内容", icon: "text" },
  { key: "pdf", group: "工具", title: "PDF 工具箱", description: "选择 PDF，合并、拆分或提取页", icon: "pdf" },
  { key: "excel", group: "工具", title: "Excel 工具箱", description: "选择表格，合并、拆分或转换格式", icon: "excel" },
  { key: "compare", group: "工具", title: "表格比对", description: "选择两张表，按关键列找差异", icon: "compare" },
  { key: "settings", group: "系统", title: "设置", description: "外观、输出与运行偏好", icon: "settings" },
  { key: "about", group: "系统", title: "关于", description: "版本信息与在线更新", icon: "about" },
];

// 工作台只从完整导航中挑选高频入口，标题、说明和图标继续复用同一对象。
export const HOME_SHORTCUTS = NAV_ITEMS.filter((item) =>
  ["attendance", "reconcile", "arrival", "pivot", "purchase", "delivery", "supplier_batch", "library", "invoice", "currency"].includes(item.key),
);
