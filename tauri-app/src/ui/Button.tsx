/** 统一视觉变体、尺寸、加载状态和禁用语义的基础按钮。 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

/** 加载时自动禁止重复点击并通过 aria-busy 告知辅助技术。 */
export function Button({ variant = "primary", size = "md", loading = false, className = "", children, disabled, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`fyt-button ${className}`.trim()}
      data-variant={variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <span className="fyt-button-spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export default Button;
