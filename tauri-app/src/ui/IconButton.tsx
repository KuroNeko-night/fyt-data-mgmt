/** 强制提供可访问名称和提示文本的纯图标按钮。 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * 纯图标按钮属性：刻意从原生属性中移除 `aria-label`，强制调用方通过 `label`
 * 提供可访问名称，避免无文本按钮被辅助技术忽略。
 */
export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** 无障碍名称，同时通过 data-tooltip 作为悬停提示文本。 */
  label: string;
  /** 图标按钮尺寸档位：小或中等。 */
  size?: "sm" | "md";
  /** 图标内容，通常为单个 Icon 组件。 */
  children: ReactNode;
}

/**
 * 渲染强制提供可访问名称和提示文本的纯图标按钮。
 *
 * @param props.label 必填的 aria-label 与 data-tooltip 文案。
 * @param props.type 未显式传入时默认 `button`，防止在表单中误触提交。
 * @returns 带 aria-label、data-size、data-tooltip 的按钮元素。
 */
export function IconButton({ label, size = "md", className = "", children, disabled, ...props }: IconButtonProps) {
  return (
    <button
      {...props}
      className={`fyt-icon-button ${className}`.trim()}
      data-size={size}
      data-tooltip={label}
      aria-label={label}
      disabled={disabled}
      type={props.type ?? "button"}
    >
      {children}
    </button>
  );
}

export default IconButton;
