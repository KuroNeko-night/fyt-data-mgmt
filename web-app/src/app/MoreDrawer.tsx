import { Drawer } from "../ui/Drawer";
import { Icon } from "../icons";
import type { User } from "../api";
import { isNavigationAllowed, MOBILE_MORE_KEYS, getNavigationItem, type WebRouteKey } from "./navigation";

/** 更多抽屉输入：开关状态、登录用户、三类待处理数量以及关闭/导航回调。 */
type Props = {
  open: boolean;
  user: User;
  unreadCount: number;
  pendingUsers: number;
  pendingReviews: number;
  onClose: () => void;
  onNavigate: (key: WebRouteKey) => void;
};

/**
 * 移动端更多入口抽屉：按固定顺序取导航定义，并显示对应待处理数量。
 * @param open 是否显示抽屉；关闭动画由 Drawer 组件处理。
 * @param user 登录用户，用于过滤角色不可见的入口。
 * @param unreadCount 未读消息数。
 * @param pendingUsers 待审核账号数（仅系统管理入口显示）。
 * @param pendingReviews 待确认复核任务数。
 * @param onClose 关闭抽屉回调。
 * @param onNavigate 路由切换回调。
 */
export function MoreDrawer({ open, user, unreadCount, pendingUsers, pendingReviews, onClose, onNavigate }: Props) {
  // getNavigationItem 理论上可返回空值，渲染前保留过滤以容忍导航配置调整。
  const items = MOBILE_MORE_KEYS.map((key) => getNavigationItem(key)).filter((item) => item && isNavigationAllowed(item, user.role));  // 按固定顺序取项并过滤越权入口
  // 徽标逻辑与 AppSidebar 保持一致，只有消息、任务和系统管理三个入口有数字提示。
  const badgeFor = (key: WebRouteKey) => key === "notifications" ? unreadCount : key === "tasks" ? pendingReviews : key === "users" ? pendingUsers : 0;
  return <Drawer open={open} title="更多入口" description="常用管理、资料和消息入口" onClose={onClose}>
    <nav className="fyt-more-nav" aria-label="更多入口">
      {items.map((item) => item ? <button key={item.key} type="button" onClick={() => { onNavigate(item.key); onClose(); }}><span className="fyt-more-icon"><Icon name={item.icon} size={18} /></span><span><strong>{item.label}</strong><small>{item.description}</small></span>{badgeFor(item.key) > 0 ? <b>{badgeFor(item.key) > 99 ? "99+" : badgeFor(item.key)}</b> : <Icon name="arrow" size={16} />}</button> : null)}
    </nav>
  </Drawer>;
}

export default MoreDrawer;
