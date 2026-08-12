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

/** 通用空态：优先显示可失败降级的美术资源，否则显示语义图标或占位符。 */
export function EmptyState({ title, description, action, icon, illustration, illustrationAlt, className = "" }: EmptyStateProps) {
  return <div className={`fyt-empty-state ${className}`.trim()}>{illustration ? <span className="fyt-empty-illustration-frame"><ArtAsset name={illustration} alt={illustrationAlt} className="fyt-empty-illustration" /></span> : <span className="fyt-empty-icon" aria-hidden="true">{icon ?? "—"}</span>}<h3>{title}</h3>{description ? <p>{description}</p> : null}{action ? <div>{action}</div> : null}</div>;
}

export default EmptyState;
