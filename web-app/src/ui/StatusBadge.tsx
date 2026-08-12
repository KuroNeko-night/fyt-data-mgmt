import { STATUS_DEFINITIONS, type StatusKey } from "./status";

export interface StatusBadgeProps {
  status: StatusKey;
  className?: string;
}

/** 根据统一状态定义渲染色调、符号和中文标签。 */
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
