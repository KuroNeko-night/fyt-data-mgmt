/**
 * 通用空态组件：用于列表、详情页等没有数据时的统一展示。
 * 优先使用可失败降级的美术资源，其次使用图标或占位符，始终保留标题与可选操作入口。
 */
import type { ReactNode } from "react";
import ArtAsset from "./ArtAsset";

/** EmptyState 组件属性。 */
export interface EmptyStateProps {
  /** 空态标题。 */
  title: string;
  /** 补充说明文字。 */
  description?: string;
  /** 可选操作，通常放“新建/刷新”等按钮。 */
  action?: ReactNode;
  /** 无美术资源时的语义图标，默认显示占位符。 */
  icon?: ReactNode;
  /** 美术资源文件名，传入后优先于 icon 显示。 */
  illustration?: string;
  /** 美术资源替代文本，纯装饰时可省略。 */
  illustrationAlt?: string;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 通用空态：优先显示可失败降级的美术资源，否则显示语义图标或占位符。
 * @param title 标题。
 * @param description 说明文字。
 * @param action 操作区。
 * @param icon 无美术资源时的图标。
 * @param illustration 美术资源文件名；存在时优先于 icon。
 * @param illustrationAlt 美术资源替代文本。
 */
export function EmptyState({ title, description, action, icon, illustration, illustrationAlt, className = "" }: EmptyStateProps) {
  // 图标默认使用 em dash 占位，保证视觉上始终有一个稳定中心元素。
  return <div className={`fyt-empty-state ${className}`.trim()}>{illustration ? <span className="fyt-empty-illustration-frame"><ArtAsset name={illustration} alt={illustrationAlt} className="fyt-empty-illustration" /></span> : <span className="fyt-empty-icon" aria-hidden="true">{icon ?? "—"}</span>}<h3>{title}</h3>{description ? <p>{description}</p> : null}{action ? <div>{action}</div> : null}</div>;
}

export default EmptyState;
