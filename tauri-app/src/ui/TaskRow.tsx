/**
 * 任务列表行 TaskRow。
 *
 * 任务状态、标题、时间、错误和操作区的统一列表行；配合 StatusBadge 展示注册状态，
 * 供任务中心、批次跟踪等列表页复用，业务数据由调用方组织后传入。
 */
import type { ReactNode } from "react";
import StatusBadge from "./StatusBadge";
import type { StatusKey } from "./status";

/** TaskRow 组件的输入属性。 */
export interface TaskRowProps {
  /** 任务标题，作为主要内容显示。 */
  title: string;
  /** 注册的任务状态键，交给 StatusBadge 渲染。 */
  status: StatusKey;
  /** 任务时间说明，可选。 */
  time?: string;
  /** 标题旁的附加元信息（如批次、操作人），可选。 */
  meta?: ReactNode;
  /** 错误摘要，存在时显示在任务信息区。 */
  error?: string;
  /** 行尾操作区（按钮或链接），可选。 */
  actions?: ReactNode;
  /** 提供后把标题/元信息包成打开按钮；纯展示任务不传。 */
  onOpen?: () => void;
  /** 追加到行容器上的自定义类名。 */
  className?: string;
}

/**
 * 渲染任务列表行。
 *
 * 仅在提供 `onOpen` 时把主要内容包成按钮，纯展示任务不会产生虚假交互焦点；
 * 操作区始终渲染在按钮外部，避免出现按钮嵌套按钮的非法 HTML。
 *
 * @param props 见 TaskRowProps。
 */
export function TaskRow({ title, status, time, meta, error, actions, onOpen, className = "" }: TaskRowProps) {
  // 标题、时间和错误拼成紧凑内容片段；time/meta/error 按存在性渲染，空值不占节点。
  const content = <><span className="fyt-task-title">{title}</span><span className="fyt-task-meta">{time ? <span>{time}</span> : null}{meta}</span>{error ? <span className="fyt-task-error">{error}</span> : null}</>;  // 标题、时间与错误拼成紧凑内容片段，空值不占节点
  return (
    <div className={`fyt-task-row ${className}`.trim()}>
      <StatusBadge status={status} />
      <div className="fyt-task-main">{onOpen ? <button className="fyt-task-open" type="button" onClick={onOpen}>{content}</button> : content}</div>
      {/* 操作区与打开按钮保持兄弟关系，点击操作不会触发 onOpen。 */}
      {actions ? <div className="fyt-task-actions">{actions}</div> : null}
    </div>
  );
}

export default TaskRow;
