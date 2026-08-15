/**
 * 通用卡片表面 Surface。
 *
 * 可切换语义元素、视觉层级、交互和选中状态的通用卡片表面；通过 as 选择渲染标签，
 * 使标题区、列表项或区块卡片等场景保持正确 HTML 语义，同时共享同一套表面样式。
 */
import type { HTMLAttributes, ElementType, ReactNode } from "react";

/** Surface 组件的输入属性，继承宿主元素标准属性以便透传事件与 ARIA。 */
export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  /** 渲染的元素或组件类型，默认 section。 */
  as?: ElementType;
  /** 视觉层级：default 不输出 data 属性，subtle/inverse 由样式表区分。 */
  variant?: "default" | "subtle" | "inverse";
  /** 是否呈现可交互状态（悬停/按压反馈）。 */
  interactive?: boolean;
  /** 是否呈现选中状态。 */
  selected?: boolean;
  /** 卡片内容。 */
  children?: ReactNode;
}

/**
 * 渲染卡片表面。
 *
 * 通过 `as` 保留正确 HTML 语义，样式状态使用 data 属性而不拼接大量条件类；
 * variant 为 default 或布尔态为 false 时省略对应 data 属性，保持 DOM 标记精简。
 * 除样式状态外，其余 props 原样透传给宿主元素。
 *
 * @param props 见 SurfaceProps。
 */
export function Surface({ as: Component = "section", variant = "default", interactive = false, selected = false, className = "", children, ...props }: SurfaceProps) {
  return (
    // 先展开宿主属性，再用本地样式类覆盖，避免调用方 className 被吞掉。
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
