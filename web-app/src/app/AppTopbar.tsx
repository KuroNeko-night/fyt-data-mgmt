import { Icon } from "../icons";
import type { User } from "../api";

/** 顶栏输入：当前页面标题、登录用户、主题状态以及主题/更多/退出回调。 */
type Props = {
  title: string;
  user: User;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenMore: () => void;
  onLogout: () => void;
};

/**
 * 桌面顶栏：显示当前页面标题、主题切换、账号身份和退出入口。
 * @param title 当前页面标题，由路由层维护。
 * @param user 登录用户，用于展示显示名与首字头像。
 * @param theme 当前主题；按钮图标按主题显示可切换到的另一侧。
 * @param onToggleTheme 主题切换回调。
 * @param onOpenMore 移动端宽度下打开“更多”抽屉。
 * @param onLogout 退出登录回调。
 */
export function AppTopbar({ title, user, theme, onToggleTheme, onOpenMore, onLogout }: Props) {
  // 顶栏带 data-guide="topbar" 锚点，供 GuidedTour 第三步测量。
  return <header className="fyt-shell-topbar" data-guide="topbar">
    <div className="fyt-topbar-copy"><span>峰运通 / 工作空间</span><h1>{title}</h1></div>
    <div className="fyt-topbar-actions">
      <button className="fyt-topbar-more" type="button" onClick={onOpenMore} aria-label="打开更多入口"><Icon name="grid" size={18} /><span>更多</span></button>
      <button className="fyt-topbar-theme" type="button" onClick={onToggleTheme} title={theme === "dark" ? "切换为浅色" : "切换为深色"} aria-label={theme === "dark" ? "切换为浅色" : "切换为深色"}><Icon name={theme === "dark" ? "sun" : "moon"} size={18} /></button>
      <div className="fyt-topbar-user"><div className="fyt-account-avatar" aria-hidden="true">{user.display_name.slice(0, 1)}</div><span>{user.display_name}</span></div>
      <button className="fyt-topbar-logout" type="button" onClick={onLogout} aria-label="退出登录" title="退出登录"><Icon name="logout" size={18} /></button>
    </div>
  </header>;
}

export default AppTopbar;
