import { Icon } from "../icons";
import type { User } from "../api";
import { isNavigationAllowed, NAVIGATION_ITEMS, type WebRouteKey } from "./navigation";

/** 移动导航输入：当前路由、登录用户、消息/待确认复核徽标数量以及导航与更多回调。 */
type Props = {
  activeKey: string;
  user: User;
  unreadCount: number;
  pendingReviews: number;
  onNavigate: (key: WebRouteKey) => void;
  onOpenMore: () => void;
};

/**
 * 移动端底部主导航：只展示高频入口，其余功能放入“更多”抽屉。
 * @param activeKey 当前激活路由；具体业务工作区会归属到“业务模块”入口高亮。
 * @param user 登录用户，用于按角色过滤可见入口。
 * @param unreadCount 未读消息数，合并进“更多”徽标。
 * @param pendingReviews 待确认复核任务数。
 * @param onNavigate 路由切换回调。
 * @param onOpenMore 打开“更多”抽屉。
 */
export function MobileNavigation({ activeKey, user, unreadCount, pendingReviews, onNavigate, onOpenMore }: Props) {
  // 同时应用移动端主入口标记和角色权限，保证按钮数量稳定且不越权展示。
  const items = NAVIGATION_ITEMS.filter((item) => item.mobilePrimary && isNavigationAllowed(item, user.role));
  // “更多”徽标合并消息与待确认复核数，保持入口汇总口径与桌面侧栏一致。
  return <nav className="fyt-mobile-nav" aria-label="移动端主导航">
    {items.map((item) => {
      // 任一具体业务工作区都归属于“业务模块”主入口。
      const active = item.key === "features" ? activeKey === "features" || activeKey.startsWith("feature:") : activeKey === item.key;
      const badge = item.key === "tasks" ? pendingReviews : item.key === "notifications" ? unreadCount : 0;
      return <button key={item.key} type="button" className={active ? "is-active" : ""} onClick={() => onNavigate(item.key)} aria-current={active ? "page" : undefined}><Icon name={item.icon} size={19} /><span>{item.label}</span>{badge > 0 ? <b>{badge > 99 ? "99+" : badge}</b> : null}</button>;
    })}
    <button type="button" onClick={onOpenMore}><Icon name="plus" size={19} /><span>更多</span>{unreadCount + pendingReviews > 0 ? <b>{unreadCount + pendingReviews > 99 ? "99+" : unreadCount + pendingReviews}</b> : null}</button>
  </nav>;
}

export default MobileNavigation;
