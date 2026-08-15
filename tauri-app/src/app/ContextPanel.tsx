/** 桌面端右侧快捷工作台：展示当前业务、近期任务和固定常用入口。 */
import Icon from "../components/Icon";
import type { NavItem } from "./navigation";
import type { TaskResult } from "../lib/bridge";

/**
 * 快捷工作台所需的当前业务、任务摘要与开关回调。
 *
 * `tasks` 允许为 null，面板会把空任务列表与尚未读取到的状态都展示为空提示，
 * 不阻塞其他区域使用。
 */
interface ContextPanelProps {
  activeItem: NavItem;
  tasks: TaskResult | null;
  open: boolean;
  onClose: () => void;
  onNavigate: (key: string) => void;
}

/**
 * 把 Core 任务状态键转换为客户可读短文本。
 *
 * @param status Core 持久化的任务状态键（ok/running/failed/interrupted 等）。
 * @returns 面向客户的短文本；未知状态回退为“等待处理”，避免界面出现内部键。
 */
function taskStatusText(status: string) {
  if (status === "ok") return "已完成";
  if (status === "running") return "处理中";
  if (status === "failed") return "处理失败";
  if (status === "interrupted") return "已中断";
  return "等待处理";
}

/**
 * 渲染可覆盖主内容的快捷面板。
 *
 * 背景按钮提供鼠标关闭入口，`aria-hidden` 让关闭状态不被辅助技术当作当前内容；任务
 * 只展示最近四条并统一跳转任务中心，面板不复制任务详情逻辑。
 */
export default function ContextPanel({ activeItem, tasks, open, onClose, onNavigate }: ContextPanelProps) {
  return (
    <>
      {open ? <button className="fyt-tauri-panel-backdrop" type="button" aria-label="关闭快捷工作台" onClick={onClose} /> : null}
      <aside className={`fyt-tauri-context-panel${open ? " is-open" : ""}`} data-tour="quick-panel" aria-hidden={!open}>
        <div className="fyt-tauri-context-header">
          <div><strong>快捷工作台</strong><span>最近任务与常用入口</span></div>
          <button className="fyt-tauri-close-button" type="button" aria-label="关闭快捷工作台" title="关闭快捷工作台" onClick={onClose}>×</button>
        </div>
        <div className="fyt-tauri-context-body">
          <section className="fyt-tauri-context-section">
            <div className="fyt-tauri-context-kicker">当前工作</div>
            <strong className="fyt-tauri-context-current">{activeItem.title}</strong>
            <span className="fyt-tauri-status" data-tone="success"><i />可以开始处理</span>
          </section>
          <section className="fyt-tauri-context-section">
            <div className="fyt-tauri-context-section-heading"><h2>最近任务</h2><button className="fyt-tauri-text-button" type="button" onClick={() => onNavigate("tasks")}>查看全部</button></div>
            {tasks?.items.length ? (
              <div className="fyt-tauri-quick-task-list">
                {tasks.items.slice(0, 4).map((task) => (
                  <button type="button" key={task.id} onClick={() => onNavigate("tasks")}>
                    <span><strong>{task.title}</strong><small>{taskStatusText(task.status)}</small></span><Icon name="arrow" size={15} />
                  </button>
                ))}
              </div>
            ) : <p className="fyt-tauri-context-empty">完成一次业务处理后，任务记录会显示在这里。</p>}
          </section>
          <section className="fyt-tauri-context-section">
            <h2>常用入口</h2>
            <div className="fyt-tauri-quick-links">
              <button type="button" onClick={() => onNavigate("tasks")}><Icon name="tasks" size={17} />任务中心</button>
              <button type="button" onClick={() => onNavigate("library")}><Icon name="database" size={17} />数据资料</button>
              <button type="button" onClick={() => onNavigate("settings")}><Icon name="settings" size={17} />系统设置</button>
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}
