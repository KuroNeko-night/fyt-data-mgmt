/* Web 客户端的最小 Vite 配置，部署路径和静态资源策略由服务端统一处理。 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()], // 只启用 React 编译能力，不在构建层复制认证、代理或业务规则。
});
