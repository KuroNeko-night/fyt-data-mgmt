/** 可选美术资源、图标、说明和操作入口的统一空状态。 */
import type { ReactNode } from "react";
import ArtAsset from "./ArtAsset";

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
  illustration?: string;
  illustrationAlt?: string;
  className?: string;
}

/** 优先展示业务美术图；未提供时使用轻量图标占位，内容与操作仍保持真实 HTML。 */
export function EmptyState({ title, description, action, icon, illustration, illustrationAlt, className = "" }: EmptyStateProps) {
  return <div className={`fyt-empty-state ${className}`.trim()}>{illustration ? <span className="fyt-empty-illustration-frame"><ArtAsset name={illustration} alt={illustrationAlt} className="fyt-empty-illustration" /></span> : <span className="fyt-empty-icon" aria-hidden="true">{icon ?? "—"}</span>}<h3>{title}</h3>{description ? <p>{description}</p> : null}{action ? <div>{action}</div> : null}</div>;
}

export default EmptyState;
