/** 带 CSS 降级占位的生成美术资源组件。 */
import { useState } from "react";

/** 生成美术资源组件属性。 */
type Props = {
  /** 生成资源文件名，相对于 `/illustrations/generated/` 目录。 */
  name: string;
  /** 替代文本；为空时资源视为纯装饰并对辅助技术隐藏。 */
  alt?: string;
  /** 附加到根元素（图片或降级占位）的类名。 */
  className?: string;
  /** 原生加载策略：急切加载或延迟加载，默认 lazy。 */
  loading?: "eager" | "lazy";
};

/** 把资源文件名转换为稳定 CSS 类片段，供每张图定义专属降级图案。 */
function fallbackName(name: string) {
  return name.replace(/\.[^.]+$/, "").replace(/[^a-z0-9-]/gi, "-");
}

/**
 * 优先加载同步到 public 的生成图片，加载失败时切换为不依赖网络的 CSS 图形。
 *
 * 有替代文本的资源按图片语义暴露给辅助技术，纯装饰资源则隐藏；失败状态只在当前资源
 * 名称生命周期内维护，不触发重复加载循环。
 *
 * @param name 生成资源文件名，同时用于构造专属降级 CSS 类。
 * @param alt 替代文本；为空时资源按纯装饰处理。
 * @param className 附加类名，用于调整布局与尺寸。
 * @param loading 原生 lazy/eager 加载策略。
 * @returns 成功时返回 img 元素，加载失败一次后返回 CSS 降级 span。
 */
export function ArtAsset({ name, alt = "", className = "", loading = "lazy" }: Props) {
  const [failed, setFailed] = useState(false);  // 失败状态只在当前资源生命周期内维护
  const assetName = fallbackName(name);
  const fallbackClass = `fyt-art-fallback fyt-art-${assetName} fyt-art-fallback-${assetName}`;
  if (failed) {  // 失败一次后切换 CSS 降级，不触发重复加载循环
    return <span className={`${fallbackClass} ${className}`.trim()} aria-hidden={alt ? undefined : "true"} role={alt ? "img" : undefined} aria-label={alt || undefined}><i /><b /></span>;
  }
  return <img className={`fyt-art-asset fyt-art-${assetName} ${className}`.trim()} src={`/illustrations/generated/${name}`} alt={alt} loading={loading} decoding="async" aria-hidden={alt ? undefined : "true"} onError={() => setFailed(true)} />;
}

export default ArtAsset;
