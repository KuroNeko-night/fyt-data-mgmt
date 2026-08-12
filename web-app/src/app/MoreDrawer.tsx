import { Drawer } from "../ui/Drawer";
import { Icon } from "../icons";
import type { User } from "../api";
import { isNavigationAllowed, MOBILE_MORE_KEYS, getNavigationItem, type WebRouteKey } from "./navigation";

type Props = {
  open: boolean;
  user: User;
  unreadCount: number;
  pendingUsers: number;
  pendingReviews: number;
  onClose: () => void;
  onNavigate: (key: WebRouteKey) => void;
};

/** 移动端更多入口抽屉：按固定顺序取导航定义，并显示对应待处理数量。 */
export function MoreDrawer({ open, user, unreadCount, pendingUsers, pendingReviews, onClose, onNavigate }: Props) {
  // getNavigationItem 理论上可返回空值，渲染前保留过滤以容忍导航配置调整。
  const items = MOBILE_MORE_KEYS.map((key) => getNavigationItem(key)).filter((item) => item && isNavigationAllowed(item, user.role));
  const badgeFor = (key: WebRouteKey) => key === "notifications" ? unreadCount : key === "tasks" ? pendingReviews : key === "users" ? pendingUsers : 0;
  return <Drawer open={open} title="更多入口" description="常用管理、资料和消息入口" onClose={onClose}>
    <nav className="fyt-more-nav" aria-label="更多入口">
      {items.map((item) => item ? <button key={item.key} type="button" onClick={() => { onNavigate(item.key); onClose(); }}><span className="fyt-more-icon"><Icon name={item.icon} size={18} /></span><span><strong>{item.label}</strong><small>{item.description}</small></span>{badgeFor(item.key) > 0 ? <b>{badgeFor(item.key) > 99 ? "99+" : badgeFor(item.key)}</b> : <Icon name="arrow" size={16} />}</button> : null)}
    </nav>
  </Drawer>;
}

export default MoreDrawer;
