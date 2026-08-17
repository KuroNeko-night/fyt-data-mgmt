/** 桌面端根组件：在本地 Core 工作台与服务器 Web 工作台之间选择并记住模式。 */
import { useState } from "react";
import LocalWorkbench from "./app/LocalWorkbench";
import ModePicker from "./app/ModePicker";
import RemoteWorkbench from "./app/RemoteWorkbench";

/** 本地存储键：保存上次选择的桌面工作模式。 */
const MODE_KEY = "fyt-desktop-mode";

/**
 * 从本地存储恢复上次使用方式；首次进入时显示模式选择页。
 *
 * 模式只影响当前桌面壳加载本地页面还是服务器 iframe，不迁移或合并两端数据。惰性
 * `useState` 只在首次挂载读取一次 localStorage，避免每次渲染重复访问同步存储。
 */
export default function App() {
  const [mode, setMode] = useState<"local" | "server" | null>(() => {
    const saved = localStorage.getItem(MODE_KEY);  // 惰性初始化只读一次本地存储，避免每次渲染访问同步存储
    return saved === "local" || saved === "server" ? saved : null;
  });
  if (mode === null) {
    // 用户明确选择后才持久化，避免未完成首次引导时错误锁定模式。
    return <ModePicker onPick={(next) => { localStorage.setItem(MODE_KEY, next); setMode(next); }} />;  // 用户明确选择后才持久化，避免锁定错误模式
  }
  if (mode === "server") {
    // 返回本地模式同时更新持久偏好，下次启动无需再次经过选择页。
    return <RemoteWorkbench onBack={() => { localStorage.setItem(MODE_KEY, "local"); setMode("local"); }} />;  // 返回本地同时更新持久偏好，下次启动无需再选择
  }
  return <LocalWorkbench />;
}
