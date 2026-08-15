/** 首次进入时选择本地 Core 或服务器 Web 工作台，并保存服务器地址。 */
import { useState } from "react";
import Icon from "../components/Icon";
import ArtAsset from "../ui/ArtAsset";

/** 本地存储键：保存最近连接过的服务器地址。 */
const SERVER_URL_KEY = "fyt-server-url";

/**
 * 读取最近连接过的服务器地址。
 *
 * @returns 用户上次保存的地址；没有记录时回退到本机默认 Web 服务端口。
 */
function serverUrlOrDefault() {
  return localStorage.getItem(SERVER_URL_KEY) || "http://127.0.0.1:8787";
}

/**
 * 服务器地址只在用户点击连接时持久化，输入过程不会覆盖上一条可用地址。
 *
 * 本组件不主动探测服务器可达性，连接结果由 iframe 页面展示；这样模式选择不会因
 * 临时网络抖动卡住，用户仍可返回本地业务。
 */
export default function ModePicker({ onPick }: { onPick: (mode: "local" | "server") => void }) {
  const [url, setUrl] = useState(serverUrlOrDefault);
  return (
    <main className="fyt-tauri-mode-picker">
      <div className="fyt-tauri-mode-brand"><span className="fyt-tauri-brand-mark" aria-hidden="true">峰</span><span><strong>峰运通</strong><small>数据管理系统</small></span></div>
      <div className="fyt-tauri-mode-heading"><span className="fyt-tauri-eyebrow">首次进入</span><h1>选择使用方式</h1><p>离线模式使用本机数据与业务处理；连接服务器后使用局域网服务器上的账号与数据。</p></div>
      <div className="fyt-tauri-mode-visual"><ArtAsset name="remote-bridge.webp" alt="本地资料与服务器工作台之间的连接示意" loading="eager" /></div>
      <div className="fyt-tauri-mode-options">
        <button className="fyt-tauri-mode-option" type="button" onClick={() => onPick("local")}>
          <span className="fyt-tauri-mode-icon"><Icon name="laptop" size={22} /></span>
          <strong>离线使用</strong>
          <small>本机直接处理，不连接服务器，数据保存在当前电脑。</small>
          <span className="fyt-tauri-mode-action">进入离线工作台 <Icon name="arrow" size={15} /></span>
        </button>
        <div className="fyt-tauri-mode-option fyt-tauri-mode-option-server">
          <span className="fyt-tauri-mode-icon"><Icon name="server" size={22} /></span>
          <strong>连接服务器</strong>
          <small>像 Web 端一样登录公司服务器，账号、任务与数据云端共享。</small>
          <label className="fyt-tauri-mode-url"><span>服务器地址</span><input value={url} placeholder="例如 http://192.168.1.10:8787" onChange={(event) => setUrl(event.target.value)} /></label>
          <button className="fyt-tauri-mode-action" type="button" onClick={() => { localStorage.setItem(SERVER_URL_KEY, url.trim() || "http://127.0.0.1:8787"); onPick("server"); }}>连接服务器 <Icon name="arrow" size={15} /></button>
        </div>
      </div>
      <p className="fyt-tauri-mode-hint">服务器地址由管理员提供；两种模式可在设置中切换。</p>
    </main>
  );
}

export { serverUrlOrDefault };
