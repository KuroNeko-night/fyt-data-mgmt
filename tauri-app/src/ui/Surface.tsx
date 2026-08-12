/** 可切换语义元素、视觉层级、交互和选中状态的通用卡片表面。 */
import type { HTMLAttributes, ElementType, ReactNode } from "react";

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: ElementType;
  variant?: "default" | "subtle" | "inverse";
  interactive?: boolean;
  selected?: boolean;
  children?: ReactNode;
}

/** 通过 `as` 保留正确 HTML 语义，样式状态使用 data 属性而不拼接大量条件类。 */
export function Surface({ as: Component = "section", variant = "default", interactive = false, selected = false, className = "", children, ...props }: SurfaceProps) {
  return (
    <Component
      {...props}
      className={`fyt-surface ${className}`.trim()}
      data-variant={variant === "default" ? undefined : variant}
      data-interactive={interactive ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
    >
      {children}
    </Component>
  );
}

export default Surface;
