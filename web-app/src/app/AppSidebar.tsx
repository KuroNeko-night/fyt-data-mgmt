import { Icon } from "../icons";
import type { User } from "../api";
import { isNavigationAllowed, isRouteActive, NAVIGATION_ITEMS, type WebRouteKey } from "./navigation";
import Brand from "./Brand";

type Props = {
  activeKey: string;
  user: User;
  pendingUsers: number;
  pendingReviews: number;
  unreadCount: number;
  onNavigate: (key: WebRouteKey) => void;
  onLogout: () => void;
};

/** 桌面侧栏：按角色过滤导航，并集中展示任务、消息和账号审核徽标。 */
export function AppSidebar({ activeKey, user, pendingUsers, pendingReviews, unreadCount, onNavigate, onLogout }: Props) {
  // 前端过滤只负责入口体验，服务端仍会对每个 API 独立执行角色鉴权。
  const visibleItems = NAVIGATION_ITEMS.filter((item) => isNavigationAllowed(item, user.role));
  // 只有三个导航项需要数字徽标，其余项统一返回零以保持渲染分支简单。
  const badgeFor = (key: WebRouteKey) => key === "notifications" ? unreadCount : key === "tasks" ? pendingReviews : key === "users" ? pendingUsers : 0;
  return <aside className="fyt-shell-sidebar" aria-label="侧栏导航">
    <div className="fyt-shell-brand"><Brand compact /></div>
    <nav className="fyt-shell-nav" aria-label="主导航">
      {visibleItems.map((item) => {
        const badge = badgeFor(item.key);
        return <button key={item.key} data-guide={`nav-${item.key}`} className={isRouteActive(item.key, activeKey) ? "is-active" : ""} type="button" onClick={() => onNavigate(item.key)} aria-label={item.label} title={item.label} aria-current={isRouteActive(item.key, activeKey) ? "page" : undefined}>
          <Icon name={item.icon} size={18} /><span>{item.label}</span>{badge > 0 ? <b aria-label={`${badge} 条待处理信息`}>{badge > 99 ? "99+" : badge}</b> : null}
        </button>;
      })}
    </nav>
    <div className="fyt-shell-account">
      <div className="fyt-account-avatar" aria-hidden="true">{user.display_name.slice(0, 1)}</div>
      <div className="fyt-account-copy"><strong>{user.display_name}</strong><span>{user.role === "admin" ? "系统管理员" : user.role === "team_leader" ? "班组长" : "业务成员"}</span></div>
      <button className="fyt-shell-logout" type="button" onClick={onLogout} aria-label="退出登录" title="退出登录"><Icon name="logout" size={18} /></button>
    </div>
  </aside>;
}

export default AppSidebar;
