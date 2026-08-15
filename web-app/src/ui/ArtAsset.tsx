/**
 * 美术资源组件：按文件名加载已登记生成的美术图片，
 * 加载失败时切换为 CSS 兜底图形，保证装饰性视觉始终可用且不影响页面可操作性。
 * 该组件只承担背景、主视觉和空态展示，业务控件与文字不使用美术资源。
 */
import { useState } from "react";

/** ArtAsset 组件属性。 */
type Props = {
  /** 资源文件名，位于 /illustrations/generated 目录下，可带扩展名。 */
  name: string;
  /** 图片替代文本；纯装饰资源可省略，省略后对辅助技术隐藏。 */
  alt?: string;
  /** 追加到根元素的外部类名。 */
  className?: string;
  /** 原生图片加载策略：eager 立即加载，lazy 懒加载（默认）。 */
  loading?: "eager" | "lazy";
};

/**
 * 把文件名转换成可安全拼接到 CSS 类名中的资源标识。
 * 先去掉最后一个扩展名，再把剩余的非字母数字字符统一替换为连字符，
 * 避免资源文件名生成非法或冲突的 CSS 类名。
 */
function fallbackName(name: string) {
  return name.replace(/\.[^.]+$/, "").replace(/[^a-z0-9-]/gi, "-");
}

/**
 * 加载已登记的生成美术资源，并在图片缺失或加载失败时切换为 CSS 兜底图形。
 * 美术只承担装饰和空态，不影响业务控件、文字和页面可操作性。
 * @param name 资源文件名，位于 /illustrations/generated 目录下。
 * @param alt 图片替代文本；纯装饰资源可省略，省略后对辅助技术隐藏。
 * @param className 追加到根元素的外部类名。
 * @param loading 原生图片加载策略，默认懒加载。
 * @returns 成功时渲染 img；加载失败一次后渲染 CSS 兜底图形，不会回退到 img。
 */
export function ArtAsset({ name, alt = "", className = "", loading = "lazy" }: Props) {
  // 图片加载失败后置位；一旦进入兜底模式就保持稳定，避免闪烁和重复请求。
  const [failed, setFailed] = useState(false);
  const assetName = fallbackName(name);
  // 同时挂载通用兜底类与按资源名生成的专用类，供全局样式和局部覆盖共同使用。
  const fallbackClass = `fyt-art-fallback fyt-art-${assetName} fyt-art-fallback-${assetName}`;
  if (failed) {
    // 有替代文本时把兜底元素声明为图片；纯装饰资源则从辅助技术中隐藏。
    return <span className={`${fallbackClass} ${className}`.trim()} aria-hidden={alt ? undefined : "true"} role={alt ? "img" : undefined} aria-label={alt || undefined}><i /><b /></span>;
  }
  return <img className={`fyt-art-asset fyt-art-${assetName} ${className}`.trim()} src={`/illustrations/generated/${name}`} alt={alt} loading={loading} decoding="async" aria-hidden={alt ? undefined : "true"} onError={() => setFailed(true)} />;
}

export default ArtAsset;
