/** 桌面端分组主导航；收起状态只改变视觉呈现，不移除可访问名称。 */
import Icon from "../components/Icon";
import { getNavigationGroups } from "./navigation";
import type { NavItem } from "./navigation";

interface AppSidebarProps {
  activeKey: string;
  collapsed: boolean;
  items: NavItem[];
  onNavigate: (key: string) => void;
  onToggle: () => void;
}

/**
 * 由导航单一事实源生成连续分组，并用当前键标注选中项。
 *
 * 收起时仍保留 `aria-label` 和原生 `title`，键盘与辅助技术不会因文字视觉隐藏而失去
 * 页面名称。点击只上报稳定业务键，实际过渡与页面切换由工作台统一处理。
 */
export default function AppSidebar({ activeKey, collapsed, items, onNavigate, onToggle }: AppSidebarProps) {
  return (
    <aside className="fyt-tauri-sidebar" data-tour="navigation">
      <div className="fyt-tauri-brand">
        <div className="fyt-tauri-brand-mark" aria-hidden="true">峰</div>
        <div className="fyt-tauri-brand-copy"><strong>峰运通</strong><span>数据管理系统</span></div>
      </div>
      <nav className="fyt-tauri-navigation" aria-label="主导航">
        {getNavigationGroups(items).map((group) => (
          <div className="fyt-tauri-navigation-group" key={group.label || "home"}>
            {group.label ? <div className="fyt-tauri-navigation-label">{group.label}</div> : null}
            {group.items.map((item) => {
              const selected = activeKey === item.key; // 同一个布尔值同时驱动视觉类和 aria-current，避免两种状态脱节。
              return (
                <button
                  className={`fyt-tauri-navigation-item${selected ? " is-selected" : ""}`}
                  type="button"
                  key={item.key}
                  aria-current={selected ? "page" : undefined}
                  aria-label={item.title}
                  title={collapsed ? item.title : undefined}
                  onClick={() => onNavigate(item.key)}
                >
                  <Icon name={item.icon} size={19} />
                  <span>{item.title}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <button className="fyt-tauri-sidebar-toggle" type="button" aria-label={collapsed ? "展开导航" : "收起导航"} title={collapsed ? "展开导航" : "收起导航"} onClick={onToggle}>
        <Icon name="collapse" size={19} />
        <span>{collapsed ? "展开导航" : "收起导航"}</span>
      </button>
    </aside>
  );
}
