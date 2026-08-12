/**
 * Web React 入口。
 *
 * 样式从设计令牌和全局基础逐层加载到具体业务页面，最后由收尾覆盖处理跨页面一致性；
 * 该顺序是层叠契约的一部分，不能随意按文件名重新排序。
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/theme.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";
import "./styles/responsive.css";
import "./styles/visuals.css";
import "./workbench.css";
import "./workflows.css";
import "./operations.css";
import "./business-results.css";
import "./daily-report.css";
import "./styles/finish.css";

// 根节点由 Vite 模板保证存在；StrictMode 用于开发期发现副作用清理和非幂等逻辑。
createRoot(document.getElementById("root")!).render(<StrictMode><div className="fyt-ui"><App /></div></StrictMode>);
