/**
 * Web 导航与角色可见性的单一配置。
 * 前端壳层、移动导航和更多抽屉都复用此表；`allowedRoles` 只控制入口展示，
 * 不承担服务端鉴权职责。
 */
import type { TaskFilter } from "../TaskCenterPage";
import type { UserRole } from "../api";

/** 稳定路由键；`feature:` 前缀的业务工作区路由不在壳层导航中定义。 */
export type WebRouteKey = "overview" | "daily-report" | "workshop" | "features" | "library" | "reports" | "tasks" | "notifications" | "security" | "users";

/** 导航入口元数据：路由键、文案、图标、移动端主入口标记与可见角色。 */
export type NavigationItem = {
  key: WebRouteKey;
  label: string;
  description: string;
  icon: string;
  mobilePrimary?: boolean;
  allowedRoles?: readonly UserRole[];
};

/**
 * 壳层导航唯一事实源。
 * 角色矩阵与 web_backend/config.py 保持一致：日清看板、报表中心、系统管理仅管理员；
 * 数据库对班组长和管理员开放；其余入口所有正常账号可见。
 */
export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  { key: "overview", label: "工作台", description: "查看当前待办、任务状态和近期变化", icon: "grid", mobilePrimary: true },
  { key: "daily-report", label: "日清看板", description: "查看当天到料、出勤、生产计划和重点事项", icon: "chart", allowedRoles: ["admin"] },
  { key: "workshop", label: "现场问题", description: "记录和查看车间现场问题", icon: "camera", mobilePrimary: true },
  { key: "features", label: "业务模块", description: "选择业务并开始处理文件", icon: "database", mobilePrimary: true },
  { key: "library", label: "数据库", description: "管理团队共享和个人资料", icon: "file", allowedRoles: ["admin", "team_leader"] },
  { key: "reports", label: "报表中心", description: "生成业务统计报表", icon: "pie", allowedRoles: ["admin"] },
  { key: "tasks", label: "任务中心", description: "查看任务进度、结果和异常", icon: "activity", mobilePrimary: true },
  { key: "notifications", label: "消息中心", description: "查看公告和定向消息", icon: "bell" },
  { key: "security", label: "账号安全", description: "管理密码和登录设备", icon: "lock" },
  { key: "users", label: "系统管理", description: "管理账号、资料和系统消息", icon: "users", allowedRoles: ["admin"] },
];

/** 移动端“更多”抽屉按此固定顺序取导航项，保证入口位置稳定。 */
export const MOBILE_MORE_KEYS: readonly WebRouteKey[] = ["daily-report", "library", "reports", "notifications", "security", "users"];

/**
 * 按稳定路由键查找导航元数据，业务功能的 `feature:` 子路由不在此表中。
 * @param key 路由键字符串。
 * @returns 命中的导航项；未命中返回 undefined。
 */
export function getNavigationItem(key: string): NavigationItem | undefined {
  return NAVIGATION_ITEMS.find((item) => item.key === key);
}

/**
 * 判断角色是否可见指定入口；未设置角色限制的页面对所有正常账号开放。
 * 该判断仅控制入口展示，服务端仍会按同一角色矩阵独立鉴权。
 * @param item 导航项；undefined 时视为不可见。
 * @param role 当前用户角色。
 */
export function isNavigationAllowed(item: NavigationItem | undefined, role: UserRole): boolean {
  return !item?.allowedRoles || item.allowedRoles.includes(role);  // 未设置角色限制即所有正常账号可见
}

/**
 * 将任意具体业务工作区视为“业务模块”导航项的激活状态。
 * @param itemKey 待判断的导航项键。
 * @param activeKey 当前激活路由。
 * @returns 是否应高亮该导航项。
 */
export function isRouteActive(itemKey: WebRouteKey, activeKey: string): boolean {
  return itemKey === "features" ? activeKey === "features" || activeKey.startsWith("feature:") : itemKey === activeKey;  // 具体业务工作区归属到“业务模块”入口高亮
}

/**
 * 把任务筛选键转换为导航或面包屑使用的简短标签。
 * @param filter 任务中心筛选键。
 * @returns 对应中文短标签；未知键按“全部”处理。
 */
export function taskFilterLabel(filter: TaskFilter): string {
  return filter === "review" ? "待确认" : filter === "failed" ? "异常" : filter === "active" ? "处理中" : filter === "completed" ? "已完成" : "全部";
}
