import type { ReactNode } from "react";
import StatusBadge from "./StatusBadge";
import type { StatusKey } from "./status";

export interface TaskRowProps {
  title: string;
  status: StatusKey;
  time?: string;
  meta?: ReactNode;
  error?: string;
  actions?: ReactNode;
  onOpen?: () => void;
  className?: string;
}

/** 任务列表基础行：状态固定在左侧，主体可选整体点击，操作区保持独立按钮语义。 */
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
