/**
 * 骨架屏组件：提供 line/title/rect 三种纯装饰占位形状。
 * 组件不提供可访问的加载说明，外层应配合 aria-busy 或可见文案一起使用。
 */
export interface SkeletonProps {
  /** 骨架形状：line 行，title 标题，rect 矩形。 */
  variant?: "line" | "title" | "rect";
  /** 自定义宽度；缺省时由 variant 对应的样式决定。 */
  width?: string;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 纯装饰加载骨架；从辅助技术中隐藏，实际加载状态由外层区域说明。
 * @param variant 骨架形状。
 * @param width 自定义宽度。
 */
export function Skeleton({ variant = "line", width, className = "" }: SkeletonProps) {
  return <span className={`fyt-skeleton ${className}`.trim()} data-variant={variant} style={width ? { width } : undefined} aria-hidden="true" />;
}

export default Skeleton;
