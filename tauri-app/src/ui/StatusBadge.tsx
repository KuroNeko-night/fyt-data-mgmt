/** 按设计令牌生成的任务状态表渲染一致色调、符号和中文标签。 */
import { STATUS_DEFINITIONS, type StatusKey } from "./status";

export interface StatusBadgeProps {
  status: StatusKey;
  className?: string;
}

/** 调用方只能传入注册状态键，避免界面出现未定义颜色或开发者状态文本。 */
export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const definition = STATUS_DEFINITIONS[status];
  return (
    <span className={`fyt-status-badge ${className}`.trim()} data-tone={definition.tone}>
      <span aria-hidden="true">{definition.symbol}</span>
      <span>{definition.label}</span>
    </span>
  );
}

export default StatusBadge;
