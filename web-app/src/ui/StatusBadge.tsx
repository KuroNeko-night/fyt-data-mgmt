/**
 * 状态徽章组件：根据统一状态定义渲染中文标签、色调和短符号。
 * 组件不内置任何状态文案，所有展示内容都来自 status.ts 的单一定义。
 */
import { STATUS_DEFINITIONS, type StatusKey } from "./status";

/** StatusBadge 组件属性。 */
export interface StatusBadgeProps {
  /** 状态键；必须是 status.ts 中已登记的稳定值。 */
  status: StatusKey;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 根据统一状态定义渲染色调、符号和中文标签。
 * @param status 状态键；未登记的值会取到 undefined，属于前端协议错误。
 */
export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  // 直接按状态键索引定义表；状态表由设计令牌同步脚本维护。
  const definition = STATUS_DEFINITIONS[status];
  return (
    <span className={`fyt-status-badge ${className}`.trim()} data-tone={definition.tone}>
      <span aria-hidden="true">{definition.symbol}</span>
      <span>{definition.label}</span>
    </span>
  );
}

export default StatusBadge;
