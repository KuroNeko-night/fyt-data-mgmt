import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  label: string;
  size?: "sm" | "md";
  children: ReactNode;
}

/** 图标按钮强制要求可访问名称，并把同一名称作为桌面端悬浮提示。 */
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
