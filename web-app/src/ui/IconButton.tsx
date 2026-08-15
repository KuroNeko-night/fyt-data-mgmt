/**
 * 图标按钮组件：强制提供可访问名称，并把同一名称用于桌面端悬浮提示。
 * 排除原生 aria-label 避免调用方漏写；type 默认按 button 处理，防止表单内意外提交。
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** 图标按钮属性：在原生 button 属性基础上用 label 统一生成无障碍名称。 */
export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** 按钮可访问名称，同时作为桌面端悬浮提示。 */
  label: string;
  /** 尺寸档位，默认 md。 */
  size?: "sm" | "md";
  /** 图标内容。 */
  children: ReactNode;
}

/**
 * 图标按钮强制要求可访问名称，并把同一名称作为桌面端悬浮提示。
 * @param label 可访问名称；aria-label 与 data-tooltip 共用该值。
 * @param size 尺寸档位。
 * @param disabled 原生禁用状态。
 * @param props 其余原生 button 属性。
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
      type={props.type ?? "button"} // 默认不是 submit，避免放在表单内时意外提交。
    >
      {children}
    </button>
  );
}

export default IconButton;
