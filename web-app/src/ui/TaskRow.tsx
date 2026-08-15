/**
 * 任务行组件：展示任务标题、状态徽章、时间/元信息和错误摘要。
 * 主体在可点击与只读两种模式间复用同一套内容节点，操作区保持独立按钮语义。
 */
import type { ReactNode } from "react";
import StatusBadge from "./StatusBadge";
import type { StatusKey } from "./status";

/** TaskRow 组件属性。 */
export interface TaskRowProps {
  /** 任务标题。 */
  title: string;
  /** 任务状态键，交给 StatusBadge 统一展示。 */
  status: StatusKey;
  /** 时间等单行摘要信息。 */
  time?: string;
  /** 其他元信息节点。 */
  meta?: ReactNode;
  /** 错误摘要；存在时以错误样式显示。 */
  error?: string;
  /** 右侧操作区，保持独立按钮语义。 */
  actions?: ReactNode;
  /** 主体点击回调；提供后主体渲染为按钮，否则为只读容器。 */
  onOpen?: () => void;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 任务列表基础行：状态固定在左侧，主体可选整体点击，操作区保持独立按钮语义。
 * @param title 任务标题。
 * @param status 状态键。
 * @param time 时间信息。
 * @param meta 元信息。
 * @param error 错误摘要。
 * @param actions 操作区。
 * @param onOpen 主体点击回调；缺省时主体为只读容器。
 */
export function TaskRow({ title, status, time, meta, error, actions, onOpen, className = "" }: TaskRowProps) {
  // 主体内容只构造一次，在可点击按钮和只读容器两种模式之间复用。
  const content = <><span className="fyt-task-title">{title}</span><span className="fyt-task-meta">{time ? <span>{time}</span> : null}{meta}</span>{error ? <span className="fyt-task-error">{error}</span> : null}</>;
  return (
    <div className={`fyt-task-row ${className}`.trim()}>
      <StatusBadge status={status} />
      <div className="fyt-task-main">{onOpen ? <button className="fyt-task-open" type="button" onClick={onOpen}>{content}</button> : content}</div>
      {actions ? <div className="fyt-task-actions">{actions}</div> : null}
    </div>
  );
}

export default TaskRow;
