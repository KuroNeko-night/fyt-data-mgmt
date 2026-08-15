/**
 * 状态提示组件：按业务结果色调展示提示，并通过 role 区分警报与普通状态，
 * 使错误/警告能被打断式朗读，而信息和成功提示保持礼貌播报。
 */
import type { ReactNode } from "react";

/** 提示色调：info 信息，success 成功，warning 警告，error 错误。 */
export type NoticeTone = "info" | "success" | "warning" | "error";

/** Notice 组件属性。 */
export interface NoticeProps {
  /** 提示色调，默认 info。 */
  tone?: NoticeTone;
  /** 可选标题，渲染为加粗首行。 */
  title?: string;
  /** 提示正文。 */
  children: ReactNode;
  /** 关闭回调；提供后才渲染关闭按钮。 */
  onClose?: () => void;
  /** 关闭按钮的可访问名称，默认“关闭提示”。 */
  closeLabel?: string;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 状态提示：错误和警告使用 alert，普通信息与成功提示使用较温和的 status。
 * @param tone 提示色调，决定角色与图标。
 * @param title 标题。
 * @param children 正文。
 * @param onClose 关闭回调；缺省时不渲染关闭按钮。
 * @param closeLabel 关闭按钮可访问名称。
 */
export function Notice({ tone = "info", title, children, onClose, closeLabel = "关闭提示", className = "" }: NoticeProps) {
  return (
    <div className={`fyt-notice ${className}`.trim()} data-tone={tone} role={tone === "error" || tone === "warning" ? "alert" : "status"} aria-live="polite">
      {/* 图标字符只承担视觉提示并已对辅助技术隐藏；具体样式由 data-tone 决定。 */}
      <span className="fyt-notice-mark" aria-hidden="true">{tone === "success" ? "✓" : tone === "error" ? "!" : tone === "warning" ? "!" : "i"}</span>
      <div className="fyt-notice-content">
        {title ? <strong className="fyt-notice-title">{title}</strong> : null}
        <div>{children}</div>
      </div>
      {onClose ? <button className="fyt-notice-close" type="button" onClick={onClose} aria-label={closeLabel}>×</button> : null}
    </div>
  );
}

export default Notice;
