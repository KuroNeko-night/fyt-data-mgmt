/** 带 CSS 降级占位的生成美术资源组件。 */
import { useState } from "react";

type Props = {
  name: string;
  alt?: string;
  className?: string;
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
 */
export function ArtAsset({ name, alt = "", className = "", loading = "lazy" }: Props) {
  const [failed, setFailed] = useState(false);
  const assetName = fallbackName(name);
  const fallbackClass = `fyt-art-fallback fyt-art-${assetName} fyt-art-fallback-${assetName}`;
  if (failed) {
    return <span className={`${fallbackClass} ${className}`.trim()} aria-hidden={alt ? undefined : "true"} role={alt ? "img" : undefined} aria-label={alt || undefined}><i /><b /></span>;
  }
  return <img className={`fyt-art-asset fyt-art-${assetName} ${className}`.trim()} src={`/illustrations/generated/${name}`} alt={alt} loading={loading} decoding="async" aria-hidden={alt ? undefined : "true"} onError={() => setFailed(true)} />;
}

export default ArtAsset;
