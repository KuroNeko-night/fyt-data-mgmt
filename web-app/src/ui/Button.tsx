/**
 * 通用按钮组件：用 data-* 属性表达视觉变体、尺寸和加载态，
 * 样式全部交给全局按钮类名处理，组件只负责语义、可访问状态和交互约束。
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** 按钮视觉变体：primary 主操作，secondary 次操作，ghost 轻量操作，danger 危险操作。 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
/** 按钮尺寸档位：sm 小号，md 中号，lg 大号。 */
export type ButtonSize = "sm" | "md" | "lg";

/** 通用按钮属性：继承原生 button 属性，并补充设计系统所需的变体与加载态。 */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 视觉变体，默认 primary。 */
  variant?: ButtonVariant;
  /** 尺寸档位，默认 md。 */
  size?: ButtonSize;
  /** 加载中标记：显示旋转指示、禁止点击并声明忙碌状态。 */
  loading?: boolean;
  /** 按钮内容。 */
  children: ReactNode;
}

/**
 * 通用按钮：通过数据属性选择视觉变体，并在加载时自动禁用和声明忙碌状态。
 * @param variant 视觉变体，默认 primary。
 * @param size 尺寸档位，默认 md。
 * @param loading 为 true 时禁用按钮、显示加载指示并设置 aria-busy。
 * @param disabled 原生禁用状态，会与 loading 取或。
 * @returns 原生 button 元素，不改变原生键盘与表单行为。
 */
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
