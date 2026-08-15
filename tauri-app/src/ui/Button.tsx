/** 统一视觉变体、尺寸、加载状态和禁用语义的基础按钮。 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** 按钮视觉变体：主操作、次操作、幽灵按钮与危险操作。 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
/** 按钮尺寸档位：小、中、大。 */
export type ButtonSize = "sm" | "md" | "lg";

/** 基础按钮扩展属性：在原生按钮属性之上增加视觉与状态语义。 */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 视觉变体，控制按钮颜色层级与使用场景。 */
  variant?: ButtonVariant;
  /** 尺寸档位，控制内边距与字号。 */
  size?: ButtonSize;
  /** 加载态；为 true 时自动禁用并显示旋转占位，避免重复点击。 */
  loading?: boolean;
  /** 按钮内容，由调用方保证为可渲染节点。 */
  children: ReactNode;
}

/**
 * 基础按钮：统一视觉变体、尺寸、加载态和禁用语义。
 *
 * @param props.variant 视觉变体，默认主操作样式。
 * @param props.size 尺寸档位，默认中等。
 * @param props.loading 加载态；为 true 时无论外部是否传 disabled 都会禁止点击。
 * @param props.disabled 常规禁用状态，与 loading 按“或”关系合并。
 * @returns 带 data-variant/data-size/data-loading 标记和 aria-busy 状态的按钮元素。
 */
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
