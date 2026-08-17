/** 导航单一事实源的桌面展示辅助函数。 */
import { NAV_ITEMS } from "../data/navigation";
import type { NavItem } from "../data/navigation";

/**
 * 派生当前页面的顶栏标题与描述。
 *
 * @param item 当前导航项，通常来自 `NAV_ITEMS`。
 * @returns 首页返回更贴近工作台的文案，其余页面直接复用导航业务文案。
 */
export function getPageHeading(item: NavItem) {
  if (item.key === "home") return { title: "工作台", description: "从当前任务、最近处理和常用业务开始。" };  // 首页用工作台文案，其余页面复用导航配置
  return { title: item.title, description: item.description };
}

/**
 * 按声明顺序把相邻同组导航项折叠成侧栏分组。
 *
 * 算法不按组名全局重排，确保 `NAV_ITEMS` 中配置的业务顺序原样保留；无组首页独立形成
 * 空标题分组。调用方可注入子集用于权限或测试场景。
 *
 * @param items 要分组的导航项，默认读取完整桌面导航配置。
 * @returns 连续的侧栏分组；同组项只并入紧邻分组，不会跨组回收。
 */
export function getNavigationGroups(items: NavItem[] = NAV_ITEMS) {
  return items.reduce<Array<{ label: string; items: NavItem[] }>>((groups, item) => {  // 按声明顺序折叠相邻同组项，不全局重排
    const current = groups[groups.length - 1];
    if (!item.group) {
      groups.push({ label: "", items: [item] });
    } else if (current?.label === item.group) { // 只并入紧邻的同组项，防止跨组回收导致导航顺序变化。
      current.items.push(item);
    } else {
      groups.push({ label: item.group, items: [item] });
    }
    return groups;
  }, []);
}

export type { NavItem };
