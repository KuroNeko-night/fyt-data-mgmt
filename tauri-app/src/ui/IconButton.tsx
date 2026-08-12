/** 强制提供可访问名称和提示文本的纯图标按钮。 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  label: string;
  size?: "sm" | "md";
  children: ReactNode;
}

/** 默认使用普通按钮类型，避免放入表单时意外触发提交。 */
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
