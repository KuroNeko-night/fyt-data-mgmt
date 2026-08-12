import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

/** 通用按钮：通过数据属性选择视觉变体，并在加载时自动禁用和声明忙碌状态。 */
export function Button({ variant = "primary", size = "md", loading = false, className = "", children, disabled, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`fyt-button ${className}`.trim()}
      data-variant={variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      disabled={disabled || loading} // 加载中禁止重复提交，同时尊重调用方原有禁用条件。
      aria-busy={loading || undefined}
    >
      {loading ? <span className="fyt-button-spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export default Button;
