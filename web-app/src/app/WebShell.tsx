import type { ReactNode } from "react";
import type { User } from "../api";
import type { WebRouteKey } from "./navigation";
import { Icon } from "../icons";
import AppSidebar from "./AppSidebar";
import AppTopbar from "./AppTopbar";
import MobileNavigation from "./MobileNavigation";
import MoreDrawer from "./MoreDrawer";
import "./shell.css";

/** 应用壳输入：路由、页面标题、用户、主题、在线状态、各类徽标数量与全部壳层回调。 */
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

/**
 * 组合桌面侧栏、顶栏、内容滚动区、移动端导航和更多抽屉的响应式应用壳。
 * 壳层只负责布局与导航状态展示，不承载具体业务数据请求。
 * @param activeKey 当前激活路由键。
 * @param title 当前页面标题。
 * @param user 登录用户。
 * @param theme 亮/暗主题，直接作为 data-theme 输出。
 * @param online 网络在线状态；离线时在顶栏下方显示提示条。
 * @param pendingUsers 待审核账号数。
 * @param pendingReviews 待确认复核任务数。
 * @param unreadCount 未读消息数。
 * @param moreOpen 移动端“更多”抽屉开关。
 * @param onNavigate 路由切换回调。
 * @param onToggleTheme 主题切换回调。
 * @param onOpenMore / onCloseMore 打开/关闭“更多”抽屉。
 * @param onLogout 退出登录回调。
 * @param children 当前路由渲染的业务页面，统一放进主滚动容器。
 */
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
