/* Tauri 桌面前端的开发服务与发布构建配置。 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()], // React 插件同时负责 JSX 转换和开发期快速刷新。
  clearScreen: false, // 保留 Rust、桥接和 Vite 的连续日志，便于定位跨层启动错误。
  server: {
    strictPort: true, // Tauri 配置固定指向此端口，占用时应立即失败而不是静默换端口。
    host: "127.0.0.1", // 开发服务只供本机桌面壳访问，不向局域网暴露。
    port: 1420,
    watch: {
      ignored: (filePath) => {
        // Rust 构建产物和源码变化由 Cargo 管理，交给 Vite 监听会触发重复刷新。
        const normalized = filePath.replaceAll("\\", "/");
        return normalized.endsWith("/src-tauri") || normalized.includes("/src-tauri/");
      },
    },
  },
  envPrefix: ["VITE_", "TAURI_"], // 仅允许显式前缀变量进入浏览器构建，避免泄露其他环境配置。
  build: {
    target: "es2022", // Windows 10 和 11 随 Tauri WebView2 支持该语法基线。
    sourcemap: true, // 桌面崩溃日志可映射回 TypeScript 源码，便于离线诊断。
  },
});
