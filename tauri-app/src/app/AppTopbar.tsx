/** 当前页面标题、更新提示、引导、主题和快捷面板操作栏。 */
import Icon from "../components/Icon";

interface AppTopbarProps {
  title: string;
  description: string;
  updateAvailable: string;
  dark: boolean;
  panelOpen: boolean;
  onOpenGuide: () => void;
  onToggleTheme: () => void;
  onTogglePanel: () => void;
  onOpenUpdate: () => void;
}

/** 顶栏保持无业务状态，只根据父组件快照渲染并回调用户意图。 */
export default function AppTopbar({ title, description, updateAvailable, dark, panelOpen, onOpenGuide, onToggleTheme, onTogglePanel, onOpenUpdate }: AppTopbarProps) {
  return (
    <header className="fyt-tauri-topbar">
      <div className="fyt-tauri-topbar-title" data-tour="page-heading">
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="fyt-tauri-topbar-actions">
        {updateAvailable ? <button className="fyt-tauri-update" type="button" onClick={onOpenUpdate}>发现新版 v{updateAvailable}</button> : null}
        <button className="fyt-tauri-icon-button" type="button" aria-label="查看当前页面使用引导" title="查看当前页面使用引导" onClick={onOpenGuide}><Icon name="help" size={19} /></button>
        <button className="fyt-tauri-icon-button" type="button" data-tour="appearance" aria-label={dark ? "切换为浅色主题" : "切换为深色主题"} title={dark ? "切换为浅色主题" : "切换为深色主题"} onClick={onToggleTheme}><Icon name="sun" size={19} /></button>
        <button className={`fyt-tauri-icon-button${panelOpen ? " is-active" : ""}`} type="button" aria-label={panelOpen ? "关闭快捷工作台" : "打开快捷工作台"} title={panelOpen ? "关闭快捷工作台" : "打开快捷工作台"} onClick={onTogglePanel}><Icon name="panel" size={19} /></button>
      </div>
    </header>
  );
}
