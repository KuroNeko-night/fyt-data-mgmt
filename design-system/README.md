# 峰运通设计系统

`tokens.json` 是 Web 与 Tauri 共用的设计令牌唯一事实源。

运行以下命令后，会同步生成两端的令牌、基础样式、布局样式、组件样式、响应式样式和状态映射：

```powershell
node scripts/sync-design-tokens.mjs
```

生成文件位于：

- `web-app/src/styles/`
- `tauri-app/src/styles/`
- `web-app/src/ui/status.ts`
- `tauri-app/src/ui/status.ts`

组件只能使用 `--fyt-*` 语义变量。颜色、状态和动效不使用 `blue`、`cyan`、`purple` 等视觉命名。

状态的文字、颜色语义和冗余符号由 `tokens.json.statuses` 统一维护。Web 与 Tauri 可以拥有不同的布局实现，但不得为同一状态重新命名或重新配色。

亮色、暗色由最近的 `[data-theme="dark"]` 或 `[data-theme="light"]` 容器切换；减少动画同时支持 `prefers-reduced-motion: reduce` 和 Tauri 的 `data-reduce-motion="true"`。
