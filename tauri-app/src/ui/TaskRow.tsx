/** 任务状态、标题、时间、错误和操作区的统一列表行。 */
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

/** 仅在提供 `onOpen` 时把主要内容包成按钮，纯展示任务不会产生虚假交互焦点。 */
export function TaskRow({ title, status, time, meta, error, actions, onOpen, className = "" }: TaskRowProps) {
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
