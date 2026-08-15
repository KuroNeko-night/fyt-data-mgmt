/**
 * 在登录页、侧栏和移动端复用的品牌标识；紧凑模式只由 CSS 调整文字和尺寸。
 * @param compact 是否使用紧凑尺寸；由所在壳层传入，组件本身不感知具体场景。
 */
export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`fyt-brand ${compact ? "fyt-brand-compact" : ""}`.trim()}><img src="/logo.png" alt="峰运通" /><span><strong>峰运通</strong><small>数据管理系统</small></span></div>;
}

export default Brand;
