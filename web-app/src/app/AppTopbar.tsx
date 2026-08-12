import { Icon } from "../icons";
import type { User } from "../api";

type Props = {
  title: string;
  user: User;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenMore: () => void;
  onLogout: () => void;
};

/** 桌面顶栏：显示当前页面标题、主题切换、账号身份和退出入口。 */
export function AppTopbar({ title, user, theme, onToggleTheme, onOpenMore, onLogout }: Props) {
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
