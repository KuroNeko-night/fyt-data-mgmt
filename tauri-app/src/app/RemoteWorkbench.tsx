/** 在桌面壳内嵌同一套服务器 Web 前端，并提供刷新与返回本地模式入口。 */
import { serverUrlOrDefault } from "./ModePicker";

/**
 * 服务器工作台壳层的属性。
 *
 * `url` 缺省时读取 ModePicker 持久化的最近地址；`onBack` 由根组件负责切回本地模式。
 */
interface RemoteWorkbenchProps {
  url?: string;
  onBack: () => void;
}

/**
 * iframe 只授予写入剪贴板这一项 Web 业务需要的能力，不获得本地 Tauri 命令权限。
 * 顶栏始终显示当前服务器地址，便于用户确认连接目标并在异常时重新加载。
 */
export default function RemoteWorkbench({ url = serverUrlOrDefault(), onBack }: RemoteWorkbenchProps) {  // iframe 只授予 clipboard-write，不获得本地 Tauri 命令权限
  return (
    <main className="fyt-tauri-remote-workbench">
      <header className="fyt-tauri-remote-toolbar">
        <div><strong>峰运通 · 服务器工作台</strong><span>{url}</span></div>
        <div className="fyt-tauri-remote-actions"><button className="fyt-tauri-secondary-button" type="button" onClick={() => window.location.reload()}>重新加载</button><button className="fyt-tauri-primary-button" type="button" onClick={onBack}>返回本地模式</button></div>
      </header>
      <iframe src={url} title="峰运通服务器工作台" allow="clipboard-write" />
    </main>
  );
}
