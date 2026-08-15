/**
 * 通用卡片表面组件：可切换语义元素（section/div/li 等），
 * 通过 data-* 属性表达视觉变体、可交互和选中态，样式交由全局表面类名处理。
 */
import type { HTMLAttributes, ElementType, ReactNode } from "react";

/** Surface 组件属性：继承通用元素属性并增加表面语义。 */
export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  /** 渲染使用的语义元素，默认 section。 */
  as?: ElementType;
  /** 视觉变体：default 默认，subtle 浅色，inverse 反色。 */
  variant?: "default" | "subtle" | "inverse";
  /** 可交互标记，用于附加悬停/聚焦样式。 */
  interactive?: boolean;
  /** 选中态标记。 */
  selected?: boolean;
  /** 卡片内容。 */
  children?: ReactNode;
}

/**
 * 可选择语义元素的通用卡片表面，通过数据属性组合视觉变体与交互状态。
 * @param as 渲染元素，默认 section；传入的组件需支持 className 与 children。
 * @param variant 视觉变体。
 * @param interactive 是否附加交互态样式。
 * @param selected 是否显示选中态。
 */
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
