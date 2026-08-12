import type { ReactNode } from "react";
import type { User } from "../api";
import type { WebRouteKey } from "./navigation";
import { Icon } from "../icons";
import AppSidebar from "./AppSidebar";
import AppTopbar from "./AppTopbar";
import MobileNavigation from "./MobileNavigation";
import MoreDrawer from "./MoreDrawer";
import "./shell.css";

type Props = {
  activeKey: string;
  title: string;
  user: User;
  theme: "light" | "dark";
  online: boolean;
  pendingUsers: number;
  pendingReviews: number;
  unreadCount: number;
  moreOpen: boolean;
  onNavigate: (key: WebRouteKey) => void;
  onToggleTheme: () => void;
  onOpenMore: () => void;
  onCloseMore: () => void;
  onLogout: () => void;
  children: ReactNode;
};

/** 组合桌面侧栏、顶栏、内容滚动区、移动端导航和更多抽屉的响应式应用壳。 */
export function WebShell({ activeKey, title, user, theme, online, pendingUsers, pendingReviews, unreadCount, moreOpen, onNavigate, onToggleTheme, onOpenMore, onCloseMore, onLogout, children }: Props) {
  return <div className="fyt-shell" data-theme={theme}>
    <AppSidebar activeKey={activeKey} user={user} pendingUsers={pendingUsers} pendingReviews={pendingReviews} unreadCount={unreadCount} onNavigate={onNavigate} onLogout={onLogout} />
    <main className="fyt-shell-main">
      <AppTopbar title={title} user={user} theme={theme} onToggleTheme={onToggleTheme} onOpenMore={onOpenMore} onLogout={onLogout} />
      {!online ? <div className="fyt-offline-banner"><Icon name="activity" size={16} />当前网络不可用，已暂停同步，连接恢复后会自动更新</div> : null}
      {/* 业务页面统一放进唯一主滚动容器，避免导航随页面内容滚出视野。 */}
      <div className="fyt-shell-scroll">{children}</div>
    </main>
    <MobileNavigation activeKey={activeKey} user={user} unreadCount={unreadCount} pendingReviews={pendingReviews} onNavigate={onNavigate} onOpenMore={onOpenMore} />
    <MoreDrawer open={moreOpen} user={user} unreadCount={unreadCount} pendingUsers={pendingUsers} pendingReviews={pendingReviews} onClose={onCloseMore} onNavigate={onNavigate} />
  </div>;
}

export default WebShell;
