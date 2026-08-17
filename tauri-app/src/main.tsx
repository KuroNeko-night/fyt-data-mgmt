/**
 * Tauri React 前端入口。
 *
 * 样式按“令牌—主题—基础—布局—组件—页面—响应式—最终覆盖”的顺序加载；
 * 后面的专项样式可以在不提高选择器权重的情况下覆盖前层默认值。
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/theme.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";
import "./styles/shell.css";
import "./styles/pages.css";
import "./styles/page-surfaces.css";
import "./styles/page-workflows.css";
import "./styles/page-tools.css";
import "./styles/business-results.css";
import "./styles/responsive.css";
import "./styles/visuals.css";
import "./styles/finish.css";

// `root` 由受控的 Vite HTML 模板提供；StrictMode 在开发期帮助发现非幂等副作用。
createRoot(document.getElementById("root")!).render(  // root 由受控的 Vite HTML 模板提供
  <StrictMode>
    <div className="fyt-ui"><App /></div>
  </StrictMode>,
);
