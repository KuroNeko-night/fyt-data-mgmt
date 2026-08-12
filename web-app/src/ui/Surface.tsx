import type { HTMLAttributes, ElementType, ReactNode } from "react";

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: ElementType;
  variant?: "default" | "subtle" | "inverse";
  interactive?: boolean;
  selected?: boolean;
  children?: ReactNode;
}

/** 可选择语义元素的通用卡片表面，通过数据属性组合视觉变体与交互状态。 */
export function Surface({ as: Component = "section", variant = "default", interactive = false, selected = false, className = "", children, ...props }: SurfaceProps) {
  return (
    <Component
      {...props}
      className={`fyt-surface ${className}`.trim()}
      data-variant={variant === "default" ? undefined : variant} // 默认值省略属性，减少无意义选择器覆盖。
      data-interactive={interactive ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
    >
      {children}
    </Component>
  );
}

export default Surface;
