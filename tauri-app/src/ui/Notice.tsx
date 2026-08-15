/**
 * 全局内联提示组件 Notice。
 *
 * 统一信息、成功、警告和错误提示的状态语义与可选关闭操作，供任务结果、表单反馈和
 * 空态引导等场景复用；样式类与设计令牌配合，业务文案由调用方通过 children 提供。
 */
import type { ReactNode } from "react";

/** 提示语气。info/success 走普通状态播报，warning/error 走告警语义。 */
export type NoticeTone = "info" | "success" | "warning" | "error";

/** Notice 组件的输入属性。 */
export interface NoticeProps {
  /** 提示语气，默认 info。 */
  tone?: NoticeTone;
  /** 加粗标题行；缺省时不渲染标题节点。 */
  title?: string;
  /** 提示正文内容，必填。 */
  children: ReactNode;
  /** 提供后渲染关闭按钮；不提供则整条提示不可手动关闭。 */
  onClose?: () => void;
  /** 关闭按钮的无障碍名称，默认“关闭提示”。 */
  closeLabel?: string;
  /** 追加到容器上的自定义类名。 */
  className?: string;
}

/**
 * 渲染一条内联提示条。
 *
 * 警告与错误使用 alert，普通信息与成功使用 status，避免非紧急提示打断辅助技术用户；
 * aria-live 统一为 polite，确保动态插入的提示不会在读屏当前内容时被强行抢话。
 *
 * @param props 见 NoticeProps。
 */
export function Notice({ tone = "info", title, children, onClose, closeLabel = "关闭提示", className = "" }: NoticeProps) {
  return (
    // role 与 aria-live 承担无障碍语义；data-tone 只供样式层选择色调。
    <div className={`fyt-notice ${className}`.trim()} data-tone={tone} role={tone === "error" || tone === "warning" ? "alert" : "status"} aria-live="polite">
      {/* 符号属于视觉辅助，对读屏隐藏，语义由 role 和正文传达。 */}
      <span className="fyt-notice-mark" aria-hidden="true">{tone === "success" ? "✓" : tone === "error" ? "!" : tone === "warning" ? "!" : "i"}</span>
      <div className="fyt-notice-content">
        {title ? <strong className="fyt-notice-title">{title}</strong> : null}
        <div>{children}</div>
      </div>
      {/* 关闭操作是可选的，只有调用方传入 onClose 时才进入渲染与 Tab 顺序。 */}
      {onClose ? <button className="fyt-notice-close" type="button" onClick={onClose} aria-label={closeLabel}>×</button> : null}
    </div>
  );
}

export default Notice;
