import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * 将 design-system/tokens.json 投影为 Web 与 Tauri 完全一致的 CSS 基础层和状态类型。
 * tokens.json 是唯一可手工维护的设计令牌来源；本脚本生成的六个 CSS 文件及 status.ts
 * 不应单独编辑。字符串模板还集中维护跨端基础控件规则，避免两个前端逐渐产生视觉漂移。
 */
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tokenPath = resolve(root, "design-system", "tokens.json");
const tokens = JSON.parse(await readFile(tokenPath, "utf8"));

function cssName(value) {
  // JSON 使用 camelCase，CSS 自定义属性统一转换为短横线命名，保证调用端书写稳定。
  return value.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
}

function renderTokenBlock(category, values, theme = null) {
  /*
   * 无主题令牌只接受字符串值；主题令牌则从 {light, dark} 中选择当前分支。
   * 过滤规则可阻止对象被隐式序列化为 [object Object]，从生成阶段暴露令牌结构错误。
   */
  return Object.entries(values)
    .filter(([, value]) => {
      if (!theme) return typeof value === "string";
      return value && typeof value === "object" && theme in value;
    })
    .map(([key, value]) => {
      const resolved = theme ? value[theme] : value;
      return `  --fyt-${category}-${cssName(key)}: ${resolved};`;
    })
    .join("\n");
}

function renderTokensCss() {
  // :root 包含亮色与所有非主题令牌；暗色选择器只覆盖确实存在暗色分支的变量。
  const rootLines = [
    renderTokenBlock("", tokens.colors, "light").replaceAll("--fyt--", "--fyt-"),
    renderTokenBlock("space", tokens.spacing),
    renderTokenBlock("radius", tokens.radius),
    renderTokenBlock("control", tokens.control),
    renderTokenBlock("layout", tokens.layout),
    renderTokenBlock("motion", tokens.motion),
    renderTokenBlock("visual", tokens.visual),
    renderTokenBlock("type", tokens.typography),
    renderTokenBlock("elevation", tokens.elevation), // 同时允许 elevation 中存在与主题无关的基础值。
    renderTokenBlock("elevation", tokens.elevation, "light"),
    renderTokenBlock("icon", tokens.icon),
  ].filter(Boolean).join("\n");
  const darkLines = [
    renderTokenBlock("", tokens.colors, "dark").replaceAll("--fyt--", "--fyt-"),
    renderTokenBlock("elevation", tokens.elevation, "dark"),
  ].filter(Boolean).join("\n");
  // 减少动态效果直接把时长令牌降为 0，业务组件无需各自维护一套媒体查询。
  return `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
:root {
${rootLines}
  color-scheme: light;
}

[data-theme="dark"] {
${darkLines}
  color-scheme: dark;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --fyt-motion-fast: 0ms;
    --fyt-motion-base: 0ms;
    --fyt-motion-slow: 0ms;
  }
}
`;
}

// theme.css 只定义应用根容器和运行时减少动画开关，页面级外观由各端手写样式扩展。
const themeCss = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
:where(.fyt-ui) {
  display: block;
  width: 100%;
  min-height: 100%;
  height: 100%;
  color: var(--fyt-text);
  background: var(--fyt-canvas-gradient, var(--fyt-canvas));
  font-family: var(--fyt-type-font-sans);
  font-size: var(--fyt-type-body);
  line-height: var(--fyt-type-line-body);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

:where([data-reduce-motion="true"] .fyt-ui, .fyt-ui[data-reduce-motion="true"]) {
  --fyt-motion-fast: 0ms;
  --fyt-motion-base: 0ms;
  --fyt-motion-slow: 0ms;
}
`;

/*
 * base.css 统一浏览器基础行为、键盘焦点、表单禁用态和原生选择控件外观。
 * :where() 保持低特异性，使页面可按业务需要覆盖；复选框和单选框仍保留可访问焦点状态。
 */
const baseCss = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
:where(html, body, #root) {
  width: 100%;
  height: 100%;
  min-height: 100%;
}

:where(html) {
  background: var(--fyt-canvas);
}

:where(body) {
  min-width: 320px;
  margin: 0;
  background: var(--fyt-canvas-gradient, var(--fyt-canvas));
}

:where(.fyt-ui, .fyt-ui *) {
  box-sizing: border-box;
}

:where(.fyt-ui button, .fyt-ui input, .fyt-ui select, .fyt-ui textarea) {
  font: inherit;
}

:where(.fyt-ui button) {
  cursor: pointer;
}

:where(.fyt-ui button:disabled, .fyt-ui [aria-disabled="true"]) {
  cursor: not-allowed;
}

:where(.fyt-ui :focus-visible) {
  outline: 3px solid color-mix(in srgb, var(--fyt-focus) 34%, transparent);
  outline-offset: 2px;
}

:where(.fyt-ui input:not([type="checkbox"]):not([type="radio"]), .fyt-ui select, .fyt-ui textarea) {
  transition: color var(--fyt-motion-fast) var(--fyt-motion-ease), border-color var(--fyt-motion-fast) var(--fyt-motion-ease), background-color var(--fyt-motion-fast) var(--fyt-motion-ease), box-shadow var(--fyt-motion-fast) var(--fyt-motion-ease);
}
:where(.fyt-ui input, .fyt-ui select, .fyt-ui textarea)::placeholder { color: color-mix(in srgb, var(--fyt-text-muted) 82%, transparent); }
:where(.fyt-ui input, .fyt-ui select, .fyt-ui textarea):disabled { cursor: not-allowed; opacity: .58; }
:where(.fyt-ui input[readonly], .fyt-ui textarea[readonly]) { color: var(--fyt-text-secondary); background-color: color-mix(in srgb, var(--fyt-surface-subtle) 74%, transparent); }
:where(.fyt-ui select) {
  appearance: none;
  padding-right: 34px !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%3E%3Cpath d='m5.5 7.5 4.5 4.5 4.5-4.5' fill='none' stroke='%236BA2FF' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-position: right 10px center;
  background-repeat: no-repeat;
  background-size: 16px;
}
:where(.fyt-ui input[type="checkbox"], .fyt-ui input[type="radio"]) {
  width: 18px !important;
  height: 18px !important;
  min-width: 18px !important;
  min-height: 18px;
  flex: 0 0 18px;
  margin: 0;
  appearance: none;
  border: 1px solid color-mix(in srgb, var(--fyt-border-strong) 76%, var(--fyt-text-muted));
  outline: 0;
  background-color: color-mix(in srgb, var(--fyt-surface-subtle) 88%, transparent);
  background-position: center;
  background-repeat: no-repeat;
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--fyt-text) 8%, transparent);
  cursor: pointer;
  transition: border-color var(--fyt-motion-fast) var(--fyt-motion-ease), background-color var(--fyt-motion-fast) var(--fyt-motion-ease), box-shadow var(--fyt-motion-fast) var(--fyt-motion-ease), transform var(--fyt-motion-fast) var(--fyt-motion-ease);
}
:where(.fyt-ui input[type="checkbox"]) { border-radius: 5px; }
:where(.fyt-ui input[type="radio"]) { border-radius: 50%; }
:where(.fyt-ui input[type="checkbox"], .fyt-ui input[type="radio"]):hover { border-color: var(--fyt-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--fyt-primary) 12%, transparent); }
:where(.fyt-ui input[type="checkbox"]:checked) {
  border-color: var(--fyt-primary);
  background-color: var(--fyt-primary);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 18 18'%3E%3Cpath d='m4.2 9 3.1 3.1 6.5-6.5' fill='none' stroke='white' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  box-shadow: 0 5px 12px color-mix(in srgb, var(--fyt-primary) 24%, transparent);
}
:where(.fyt-ui input[type="checkbox"]:indeterminate) { border-color: var(--fyt-primary); background-color: var(--fyt-primary); background-image: linear-gradient(white, white); background-size: 8px 2px; }
:where(.fyt-ui input[type="radio"]:checked) { border-color: var(--fyt-primary); background-color: var(--fyt-primary); box-shadow: inset 0 0 0 4px var(--fyt-surface), 0 5px 12px color-mix(in srgb, var(--fyt-primary) 22%, transparent); }
:where(.fyt-ui input[type="checkbox"], .fyt-ui input[type="radio"]):active { transform: scale(.92); }
:where(.fyt-ui input[type="checkbox"], .fyt-ui input[type="radio"]):disabled { cursor: not-allowed; opacity: .46; }

.fyt-mono {
  font-family: var(--fyt-type-font-mono);
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
`;

// layout.css 提供少量跨端布局原语，不绑定任何具体业务页面结构。
const layoutCss = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
.fyt-content-container {
  width: min(var(--fyt-layout-content-max), calc(100% - (var(--fyt-layout-gutter-desktop) * 2)));
  margin-inline: auto;
}

.fyt-page {
  min-width: 0;
  padding: var(--fyt-space-8) 0 var(--fyt-space-12);
}

.fyt-stack {
  display: flex;
  flex-direction: column;
  gap: var(--fyt-space-6);
}

.fyt-cluster {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--fyt-space-3);
}
`;

/*
 * components.css 是双端通用 UI 契约：按钮、状态、表单、表格、空态和弹层类名由 React
 * 组件共同消费。动效只使用 opacity/transform 等低成本属性，并同时响应系统与应用内
 * 减少动画设置；对话框把滚动限制在 body，避免页面与弹层形成多层无边界滚动。
 */
const componentsCss = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
.fyt-button {
  display: inline-flex;
  min-height: var(--fyt-control-height-md);
  align-items: center;
  justify-content: center;
  gap: var(--fyt-space-2);
  padding: 0 var(--fyt-space-4);
  border: 1px solid transparent;
  border-radius: var(--fyt-radius-control);
  font-size: var(--fyt-type-body);
  font-weight: 650;
  line-height: 1;
  transition: color var(--fyt-motion-fast) var(--fyt-motion-ease), background-color var(--fyt-motion-fast) var(--fyt-motion-ease), border-color var(--fyt-motion-fast) var(--fyt-motion-ease), box-shadow var(--fyt-motion-fast) var(--fyt-motion-ease), opacity var(--fyt-motion-fast) var(--fyt-motion-ease);
}
.fyt-button[data-size="sm"] { min-height: var(--fyt-control-height-sm); padding-inline: var(--fyt-space-3); font-size: var(--fyt-type-caption); }
.fyt-button[data-size="lg"] { min-height: var(--fyt-control-height-lg); padding-inline: var(--fyt-space-5); }
.fyt-button[data-variant="primary"] { color: var(--fyt-text-on-inverse); background: var(--fyt-primary); }
.fyt-button[data-variant="primary"]:hover:not(:disabled) { background: var(--fyt-primary-strong); }
.fyt-button[data-variant="secondary"] { color: var(--fyt-text); border-color: var(--fyt-border-strong); background: var(--fyt-surface); }
.fyt-button[data-variant="secondary"]:hover:not(:disabled) { border-color: var(--fyt-primary); color: var(--fyt-primary-strong); background: var(--fyt-primary-soft); }
.fyt-button[data-variant="ghost"] { color: var(--fyt-text-secondary); background: transparent; }
.fyt-button[data-variant="ghost"]:hover:not(:disabled) { color: var(--fyt-primary-strong); background: var(--fyt-surface-subtle); }
.fyt-button[data-variant="danger"] { color: var(--fyt-text-on-inverse); background: var(--fyt-danger); }
.fyt-button[data-variant="danger"]:hover:not(:disabled) { background: color-mix(in srgb, var(--fyt-danger) 82%, var(--fyt-text)); }
.fyt-button:disabled { opacity: .48; }
.fyt-button[data-loading="true"] { pointer-events: none; }
.fyt-button-spinner { width: 14px; height: 14px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: fyt-spin 700ms linear infinite; }

.fyt-icon-button {
  position: relative;
  display: inline-grid;
  width: var(--fyt-control-target-min);
  height: var(--fyt-control-target-min);
  place-items: center;
  padding: 0;
  border: 1px solid var(--fyt-border);
  border-radius: var(--fyt-radius-control);
  color: var(--fyt-text-secondary);
  background: var(--fyt-surface);
  transition: color var(--fyt-motion-fast) var(--fyt-motion-ease), background-color var(--fyt-motion-fast) var(--fyt-motion-ease), border-color var(--fyt-motion-fast) var(--fyt-motion-ease);
}
.fyt-icon-button:hover:not(:disabled) { color: var(--fyt-primary-strong); border-color: var(--fyt-primary); background: var(--fyt-primary-soft); }
.fyt-icon-button:disabled { opacity: .48; }
.fyt-icon-button[data-size="sm"] { width: var(--fyt-control-height-sm); height: var(--fyt-control-height-sm); }
.fyt-icon-button[data-tooltip]::after { content: attr(data-tooltip); position: absolute; z-index: 20; top: calc(100% + var(--fyt-space-2)); right: 0; width: max-content; max-width: 220px; padding: 6px 8px; border: 1px solid var(--fyt-border-strong); border-radius: var(--fyt-radius-control); color: var(--fyt-text); background: var(--fyt-surface); box-shadow: var(--fyt-elevation-overlay); font-size: var(--fyt-type-caption); opacity: 0; pointer-events: none; transform: translateY(-3px); transition: opacity var(--fyt-motion-fast) var(--fyt-motion-ease), transform var(--fyt-motion-fast) var(--fyt-motion-ease); }
.fyt-icon-button[data-tooltip]:hover::after, .fyt-icon-button[data-tooltip]:focus-visible::after { opacity: 1; transform: translateY(0); }

.fyt-surface { border: 1px solid var(--fyt-border); border-radius: var(--fyt-radius-card); color: var(--fyt-text); background: var(--fyt-surface); }
.fyt-surface[data-variant="subtle"] { background: var(--fyt-surface-subtle); }
.fyt-surface[data-variant="inverse"] { border-color: var(--fyt-border-strong); color: var(--fyt-text-on-inverse); background: var(--fyt-surface-inverse); }
.fyt-surface[data-interactive="true"] { transition: border-color var(--fyt-motion-fast) var(--fyt-motion-ease), background-color var(--fyt-motion-fast) var(--fyt-motion-ease), box-shadow var(--fyt-motion-fast) var(--fyt-motion-ease); }
.fyt-surface[data-interactive="true"]:hover { border-color: var(--fyt-primary); box-shadow: var(--fyt-elevation-subtle); }
.fyt-surface[data-selected="true"] { border-color: var(--fyt-primary); background: var(--fyt-primary-soft); }

.fyt-page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--fyt-space-6); }
.fyt-page-header-copy { min-width: 0; }
.fyt-eyebrow { margin-bottom: var(--fyt-space-2); color: var(--fyt-primary-strong); font-size: var(--fyt-type-caption); font-weight: 700; }
.fyt-page-header h1 { margin: 0; color: var(--fyt-text); font-size: var(--fyt-type-title); font-weight: 700; line-height: 1.35; }
.fyt-page-header p { max-width: 720px; margin: var(--fyt-space-2) 0 0; color: var(--fyt-text-secondary); font-size: var(--fyt-type-body); line-height: var(--fyt-type-line-body); }
.fyt-page-header-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--fyt-space-2); }
.fyt-section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--fyt-space-4); }
.fyt-section-header h2, .fyt-section-header h3 { margin: 0; color: var(--fyt-text); font-size: var(--fyt-type-section); font-weight: 700; }
.fyt-section-header p { margin: var(--fyt-space-1) 0 0; color: var(--fyt-text-secondary); font-size: var(--fyt-type-caption); }

.fyt-status-badge { display: inline-flex; min-height: 28px; align-items: center; gap: 7px; padding: 0 9px; border: 1px solid transparent; border-radius: var(--fyt-radius-pill); font-size: var(--fyt-type-caption); font-weight: 650; white-space: nowrap; }
.fyt-status-badge::before { content: ""; width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: currentColor; }
.fyt-status-badge[data-tone="info"] { color: var(--fyt-info); border-color: color-mix(in srgb, var(--fyt-info) 28%, var(--fyt-border)); background: var(--fyt-info-soft); }
.fyt-status-badge[data-tone="success"] { color: var(--fyt-success); border-color: color-mix(in srgb, var(--fyt-success) 28%, var(--fyt-border)); background: var(--fyt-success-soft); }
.fyt-status-badge[data-tone="warning"] { color: var(--fyt-warning); border-color: color-mix(in srgb, var(--fyt-warning) 28%, var(--fyt-border)); background: var(--fyt-warning-soft); }
.fyt-status-badge[data-tone="danger"] { color: var(--fyt-danger); border-color: color-mix(in srgb, var(--fyt-danger) 28%, var(--fyt-border)); background: var(--fyt-danger-soft); }
.fyt-status-badge[data-tone="neutral"] { color: var(--fyt-neutral); border-color: var(--fyt-border); background: var(--fyt-neutral-soft); }

.fyt-notice { display: flex; align-items: flex-start; gap: var(--fyt-space-3); padding: var(--fyt-space-3) var(--fyt-space-4); border: 1px solid var(--fyt-border); border-radius: var(--fyt-radius-card); color: var(--fyt-text-secondary); background: var(--fyt-surface-subtle); }
.fyt-notice-mark { display: grid; width: 24px; height: 24px; flex: 0 0 24px; place-items: center; border-radius: 50%; color: currentColor; background: color-mix(in srgb, currentColor 16%, transparent); font-size: var(--fyt-type-caption); font-weight: 700; }
.fyt-notice[data-tone="info"] { color: var(--fyt-info); border-color: color-mix(in srgb, var(--fyt-info) 28%, var(--fyt-border)); background: var(--fyt-info-soft); }
.fyt-notice[data-tone="success"] { color: var(--fyt-success); border-color: color-mix(in srgb, var(--fyt-success) 28%, var(--fyt-border)); background: var(--fyt-success-soft); }
.fyt-notice[data-tone="warning"] { color: var(--fyt-warning); border-color: color-mix(in srgb, var(--fyt-warning) 28%, var(--fyt-border)); background: var(--fyt-warning-soft); }
.fyt-notice[data-tone="error"] { color: var(--fyt-danger); border-color: color-mix(in srgb, var(--fyt-danger) 28%, var(--fyt-border)); background: var(--fyt-danger-soft); }
.fyt-notice-content { min-width: 0; flex: 1; }
.fyt-notice-title { display: block; margin-bottom: 2px; color: var(--fyt-text); font-weight: 700; }
.fyt-notice p { margin: 0; color: inherit; font-size: var(--fyt-type-caption); }
.fyt-notice-close { flex: 0 0 auto; color: inherit; }

.fyt-form-field { display: grid; gap: var(--fyt-space-2); }
.fyt-form-label { display: inline-flex; align-items: center; gap: 4px; color: var(--fyt-text); font-size: var(--fyt-type-caption); font-weight: 700; }
.fyt-form-required { color: var(--fyt-danger); }
.fyt-form-control { min-width: 0; }
.fyt-form-help { margin: 0; color: var(--fyt-text-muted); font-size: var(--fyt-type-caption); }
.fyt-form-error { margin: 0; color: var(--fyt-danger); font-size: var(--fyt-type-caption); }
.fyt-form-field[data-invalid="true"] .fyt-form-control > input, .fyt-form-field[data-invalid="true"] .fyt-form-control > select, .fyt-form-field[data-invalid="true"] .fyt-form-control > textarea { border-color: var(--fyt-danger); }

.fyt-segmented-control { display: inline-flex; min-height: var(--fyt-control-height-md); align-items: stretch; padding: 3px; border: 1px solid var(--fyt-border); border-radius: var(--fyt-radius-control); background: var(--fyt-surface-subtle); }
.fyt-segmented-option { min-width: 44px; padding: 0 var(--fyt-space-3); border: 0; border-radius: 6px; color: var(--fyt-text-secondary); background: transparent; font-size: var(--fyt-type-caption); font-weight: 650; }
.fyt-segmented-option:hover { color: var(--fyt-text); }
.fyt-segmented-option[aria-checked="true"] { color: var(--fyt-primary-strong); background: var(--fyt-surface); box-shadow: var(--fyt-elevation-subtle); }

.fyt-table-wrap { overflow-x: auto; border: 1px solid var(--fyt-border); border-radius: var(--fyt-radius-card); background: var(--fyt-surface); }
.fyt-table { width: 100%; border-collapse: collapse; min-width: 620px; }
.fyt-table caption { padding: var(--fyt-space-3) var(--fyt-space-4); color: var(--fyt-text-secondary); text-align: left; font-size: var(--fyt-type-caption); }
.fyt-table th, .fyt-table td { padding: var(--fyt-space-3) var(--fyt-space-4); border-bottom: 1px solid var(--fyt-border); color: var(--fyt-text); text-align: left; vertical-align: middle; font-size: var(--fyt-type-caption); }
.fyt-table th { color: var(--fyt-text-secondary); background: var(--fyt-surface-subtle); font-weight: 700; white-space: nowrap; }
.fyt-table tr:last-child td { border-bottom: 0; }
.fyt-table tbody tr:hover td { background: var(--fyt-surface-subtle); }
.fyt-table-empty { padding: var(--fyt-space-8) var(--fyt-space-4); color: var(--fyt-text-muted); text-align: center; }

.fyt-task-row, .fyt-file-row { display: flex; min-width: 0; align-items: center; gap: var(--fyt-space-3); padding: var(--fyt-space-3) 0; border-bottom: 1px solid var(--fyt-border); }
.fyt-task-row:last-child, .fyt-file-row:last-child { border-bottom: 0; }
.fyt-task-main, .fyt-file-main { min-width: 0; flex: 1; }
.fyt-task-title, .fyt-file-name { display: block; overflow: hidden; color: var(--fyt-text); font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.fyt-task-meta, .fyt-file-meta { display: flex; flex-wrap: wrap; gap: var(--fyt-space-2); margin-top: 3px; color: var(--fyt-text-muted); font-size: var(--fyt-type-caption); }
.fyt-task-error { margin: 4px 0 0; overflow: hidden; color: var(--fyt-danger); font-size: var(--fyt-type-caption); text-overflow: ellipsis; white-space: nowrap; }
.fyt-task-actions, .fyt-file-actions { display: flex; flex: 0 0 auto; align-items: center; gap: var(--fyt-space-2); }
.fyt-task-open { min-width: 0; flex: 1; padding: 0; border: 0; color: inherit; background: transparent; text-align: left; }
.fyt-file-icon { display: grid; width: 36px; height: 36px; flex: 0 0 36px; place-items: center; border-radius: var(--fyt-radius-control); color: var(--fyt-primary-strong); background: var(--fyt-primary-soft); }

.fyt-empty-state { display: grid; justify-items: center; gap: var(--fyt-space-3); padding: var(--fyt-space-10) var(--fyt-space-6); color: var(--fyt-text-secondary); text-align: center; }
.fyt-empty-icon { display: grid; width: 44px; height: 44px; place-items: center; border-radius: var(--fyt-radius-card); color: var(--fyt-primary-strong); background: var(--fyt-primary-soft); }
.fyt-empty-state h3 { margin: 0; color: var(--fyt-text); font-size: var(--fyt-type-card); }
.fyt-empty-state p { max-width: 440px; margin: 0; font-size: var(--fyt-type-caption); }

.fyt-skeleton { display: block; min-height: 12px; border-radius: var(--fyt-radius-control); background: linear-gradient(90deg, var(--fyt-surface-subtle), var(--fyt-border), var(--fyt-surface-subtle)); background-size: 200% 100%; animation: fyt-skeleton 1.2s var(--fyt-motion-ease) infinite; }
.fyt-skeleton[data-variant="title"] { width: min(260px, 70%); min-height: 24px; }
.fyt-skeleton[data-variant="rect"] { min-height: 120px; border-radius: var(--fyt-radius-card); }
.fyt-skeleton-group { display: grid; gap: var(--fyt-space-3); }

.fyt-overlay { position: fixed; z-index: 1000; inset: 0; display: grid; padding: var(--fyt-space-6); place-items: center; background: var(--fyt-overlay); }
.fyt-dialog, .fyt-drawer { position: relative; width: min(520px, 100%); max-height: min(720px, calc(100vh - 48px)); border: 1px solid var(--fyt-border-strong); border-radius: var(--fyt-radius-container); color: var(--fyt-text); background: var(--fyt-surface); box-shadow: var(--fyt-elevation-overlay); animation: fyt-overlay-in var(--fyt-motion-base) var(--fyt-motion-ease) both; }
.fyt-dialog { display: flex; min-height: 0; flex-direction: column; overflow: hidden; }
.fyt-dialog[data-size="large"] { width: min(1120px, 100%); max-height: min(860px, calc(100vh - 48px)); }
.fyt-dialog-head, .fyt-drawer-head { display: flex; flex: 0 0 auto; align-items: flex-start; justify-content: space-between; gap: var(--fyt-space-4); padding: var(--fyt-space-6); border-bottom: 1px solid var(--fyt-border); }
.fyt-dialog-head h2, .fyt-drawer-head h2 { margin: 0; color: var(--fyt-text); font-size: var(--fyt-type-section); }
.fyt-dialog-head p, .fyt-drawer-head p { margin: var(--fyt-space-2) 0 0; color: var(--fyt-text-secondary); font-size: var(--fyt-type-caption); }
.fyt-dialog-body { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: var(--fyt-space-6); }
.fyt-drawer-body { padding: var(--fyt-space-6); }
.fyt-dialog-foot, .fyt-drawer-foot { display: flex; flex: 0 0 auto; justify-content: flex-end; gap: var(--fyt-space-2); padding: var(--fyt-space-4) var(--fyt-space-6); border-top: 1px solid var(--fyt-border); }
.fyt-drawer { width: min(420px, 100%); max-height: none; height: 100%; overflow: auto; border-radius: 0; animation-name: fyt-drawer-in; }
.fyt-overlay[data-side="left"] { place-items: stretch start; padding: 0; }
.fyt-overlay[data-side="right"] { place-items: stretch end; padding: 0; }
.fyt-overlay[data-side="left"] .fyt-drawer { animation-name: fyt-drawer-in-left; }

@keyframes fyt-spin { to { transform: rotate(360deg); } }
@keyframes fyt-skeleton { to { background-position: -200% 0; } }
@keyframes fyt-overlay-in { from { opacity: 0; transform: translateY(6px) scale(.99); } to { opacity: 1; transform: none; } }
@keyframes fyt-drawer-in { from { transform: translateX(18px); } to { transform: none; } }
@keyframes fyt-drawer-in-left { from { transform: translateX(-18px); } to { transform: none; } }

@media (prefers-reduced-motion: reduce) {
  .fyt-button-spinner, .fyt-skeleton { animation: none; }
  .fyt-button, .fyt-icon-button, .fyt-surface, .fyt-dialog, .fyt-drawer { transition: none; animation: none; }
}

[data-reduce-motion="true"] .fyt-button-spinner, [data-reduce-motion="true"] .fyt-skeleton { animation: none; }
[data-reduce-motion="true"] .fyt-button, [data-reduce-motion="true"] .fyt-icon-button, [data-reduce-motion="true"] .fyt-surface, [data-reduce-motion="true"] .fyt-dialog, [data-reduce-motion="true"] .fyt-drawer { transition: none; animation: none; }
`;

// responsive.css 只处理设计系统原语在平板和移动端的触控尺寸与重排，不复制页面断点。
const responsiveCss = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
@media (max-width: 1199px) {
  .fyt-content-container { width: min(var(--fyt-layout-content-max), calc(100% - (var(--fyt-layout-gutter-tablet) * 2))); }
}

@media (max-width: 767px) {
  .fyt-content-container { width: calc(100% - (var(--fyt-layout-gutter-mobile) * 2)); }
  .fyt-icon-button[data-size="sm"] { width: var(--fyt-control-target-min); height: var(--fyt-control-target-min); }
  .fyt-page { padding-block: var(--fyt-space-6) var(--fyt-space-10); }
  .fyt-page-header { flex-direction: column; gap: var(--fyt-space-4); }
  .fyt-page-header h1 { font-size: var(--fyt-type-title-mobile); }
  .fyt-page-header-actions { width: 100%; justify-content: flex-start; }
  .fyt-page-header-actions > * { min-height: var(--fyt-control-target-min); }
  .fyt-task-row, .fyt-file-row { align-items: flex-start; }
  .fyt-task-actions, .fyt-file-actions { align-self: center; }
  .fyt-dialog, .fyt-drawer { max-height: calc(100vh - 32px); }
  .fyt-overlay { padding: var(--fyt-space-4); }
  .fyt-dialog-foot, .fyt-drawer-foot { flex-wrap: wrap; }
  .fyt-dialog-foot .fyt-button, .fyt-drawer-foot .fyt-button { flex: 1 1 140px; }
}
`;

// 输出文件顺序同时体现依赖层级，调用端应按 tokens → theme/base → layout/components → responsive 引入。
const outputs = [
  ["tokens.css", renderTokensCss()],
  ["theme.css", themeCss],
  ["base.css", baseCss],
  ["layout.css", layoutCss],
  ["components.css", componentsCss],
  ["responsive.css", responsiveCss],
];

const targets = ["web-app/src/styles", "tauri-app/src/styles"];
for (const target of targets) {
  const targetDir = resolve(root, target);
  await mkdir(targetDir, { recursive: true });
  // 同一内存内容写入双端，避免分别渲染时受可变全局状态影响而产生差异。
  for (const [file, content] of outputs) await writeFile(resolve(targetDir, file), content, "utf8");
}

// 状态定义与 CSS 令牌来自同一 JSON；生成 TypeScript 类型后，业务组件只能使用已登记状态键。
const statusSource = `/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
export const STATUS_DEFINITIONS = ${JSON.stringify(tokens.statuses, null, 2)} as const;
export type StatusKey = keyof typeof STATUS_DEFINITIONS;
export type StatusTone = (typeof STATUS_DEFINITIONS)[StatusKey]["tone"];
`;
for (const target of ["web-app/src/ui/status.ts", "tauri-app/src/ui/status.ts"]) {
  const targetPath = resolve(root, target);
  await mkdir(dirname(targetPath), { recursive: true });
  await writeFile(targetPath, statusSource, "utf8");
}

console.log("设计令牌已同步到 Web 与 Tauri");
