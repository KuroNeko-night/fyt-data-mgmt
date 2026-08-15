/** 可选美术资源、图标、说明和操作入口的统一空状态。 */
import type { ReactNode } from "react";
import ArtAsset from "./ArtAsset";

/** 统一空状态属性：标题、说明、操作入口与可选美术资源。 */
export interface EmptyStateProps {
  /** 空状态主标题。 */
  title: string;
  /** 补充说明，解释为空原因或下一步建议。 */
  description?: string;
  /** 操作入口，通常为按钮或链接。 */
  action?: ReactNode;
  /** 未提供美术图时使用的轻量图标占位。 */
  icon?: ReactNode;
  /** 生成美术资源文件名；提供后优先于 icon 展示。 */
  illustration?: string;
  /** 美术资源的替代文本，供辅助技术读取。 */
  illustrationAlt?: string;
  /** 附加到根元素的类名。 */
  className?: string;
}

/**
 * 空状态组件：提供美术图或图标占位，以及标题、说明和可选操作区。
 *
 * @param props.illustration 传入后通过 ArtAsset 渲染并支持加载失败降级。
 * @returns 居中的空状态展示块，图标仅作装饰，真实信息由文本节点承载。
 */
export function EmptyState({ title, description, action, icon, illustration, illustrationAlt, className = "" }: EmptyStateProps) {
  return <div className={`fyt-empty-state ${className}`.trim()}>{illustration ? <span className="fyt-empty-illustration-frame"><ArtAsset name={illustration} alt={illustrationAlt} className="fyt-empty-illustration" /></span> : <span className="fyt-empty-icon" aria-hidden="true">{icon ?? "—"}</span>}<h3>{title}</h3>{description ? <p>{description}</p> : null}{action ? <div>{action}</div> : null}</div>;
}

export default EmptyState;
