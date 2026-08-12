import { useState } from "react";

type Props = {
  name: string;
  alt?: string;
  className?: string;
  loading?: "eager" | "lazy";
};

/** 把文件名转换成可安全拼接到 CSS 类名中的资源标识。 */
function fallbackName(name: string) {
  return name.replace(/\.[^.]+$/, "").replace(/[^a-z0-9-]/gi, "-");
}

/**
 * 加载已登记的生成美术资源，并在图片缺失或加载失败时切换为 CSS 兜底图形。
 * 美术只承担装饰和空态，不影响业务控件、文字和页面可操作性。
 */
export function ArtAsset({ name, alt = "", className = "", loading = "lazy" }: Props) {
  const [failed, setFailed] = useState(false);
  const assetName = fallbackName(name);
  const fallbackClass = `fyt-art-fallback fyt-art-${assetName} fyt-art-fallback-${assetName}`;
  if (failed) {
    // 有替代文本时把兜底元素声明为图片；纯装饰资源则从辅助技术中隐藏。
    return <span className={`${fallbackClass} ${className}`.trim()} aria-hidden={alt ? undefined : "true"} role={alt ? "img" : undefined} aria-label={alt || undefined}><i /><b /></span>;
  }
  return <img className={`fyt-art-asset fyt-art-${assetName} ${className}`.trim()} src={`/illustrations/generated/${name}`} alt={alt} loading={loading} decoding="async" aria-hidden={alt ? undefined : "true"} onError={() => setFailed(true)} />;
}

export default ArtAsset;
