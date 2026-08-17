/**
 * 任务状态徽章 StatusBadge。
 *
 * 按设计令牌生成的任务状态表渲染一致色调、符号和中文标签；状态定义集中在
 * status.ts，本组件只负责把注册状态转换为 UI，不自行维护状态文案或颜色。
 */
import { STATUS_DEFINITIONS, type StatusKey } from "./status";

/** StatusBadge 组件的输入属性。 */
export interface StatusBadgeProps {
  /** 注册的任务状态键，决定徽章文案、符号和色调。 */
  status: StatusKey;
  /** 追加到容器上的自定义类名。 */
  className?: string;
}

/**
 * 渲染任务状态徽章。
 *
 * 调用方只能传入注册状态键，避免界面出现未定义颜色或开发者状态文本；符号仅作
 * 视觉强调并对辅助技术隐藏，中文标签保留给读屏识别。状态键由 STATUS_DEFINITIONS
 * 推导，因此查表结果始终存在。
 *
 * @param props 见 StatusBadgeProps。
 */
export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  // StatusKey 来自 STATUS_DEFINITIONS 的键集合，不会出现查不到定义的情况。
  const definition = STATUS_DEFINITIONS[status];  // StatusKey 由状态定义推导，查表结果必然存在
  return (
    <span className={`fyt-status-badge ${className}`.trim()} data-tone={definition.tone}>
      {/* 符号是视觉提示，aria-hidden 避免读屏重复朗读。 */}
      <span aria-hidden="true">{definition.symbol}</span>
      <span>{definition.label}</span>
    </span>
  );
}

export default StatusBadge;
