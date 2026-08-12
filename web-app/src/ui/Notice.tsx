import type { ReactNode } from "react";

export type NoticeTone = "info" | "success" | "warning" | "error";

export interface NoticeProps {
  tone?: NoticeTone;
  title?: string;
  children: ReactNode;
  onClose?: () => void;
  closeLabel?: string;
  className?: string;
}

/** 状态提示：错误和警告使用 alert，普通信息与成功提示使用较温和的 status。 */
export function Notice({ tone = "info", title, children, onClose, closeLabel = "关闭提示", className = "" }: NoticeProps) {
  return (
    <div className={`fyt-notice ${className}`.trim()} data-tone={tone} role={tone === "error" || tone === "warning" ? "alert" : "status"} aria-live="polite">
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
