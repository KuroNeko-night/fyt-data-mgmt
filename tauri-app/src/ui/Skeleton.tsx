/**
 * 加载骨架占位组件 Skeleton。
 *
 * 在内容加载期间提供纯视觉占位，并通过 aria-hidden 完全对辅助技术隐藏，
 * 避免读屏逐条朗读骨架；加载状态的文字说明应由调用方单独提供。
 */

/** Skeleton 组件的输入属性。 */
export interface SkeletonProps {
  /** 骨架形状：line 单行、title 标题比例、rect 矩形块。 */
  variant?: "line" | "title" | "rect";
  /** 可选宽度，直接作为内联样式覆盖令牌默认宽度。 */
  width?: string;
  /** 追加到容器上的自定义类名。 */
  className?: string;
}

/**
 * 渲染一条不暴露给辅助技术的骨架占位。
 *
 * 变体只控制视觉比例，可选宽度通过内联样式覆盖令牌默认值；未传宽度时保持
 * 样式表默认值，避免产生多余内联样式。组件没有生命周期与数据请求副作用。
 *
 * @param props 见 SkeletonProps。
 */
export function Skeleton({ variant = "line", width, className = "" }: SkeletonProps) {
  return <span className={`fyt-skeleton ${className}`.trim()} data-variant={variant} style={width ? { width } : undefined} aria-hidden="true" />;
}

export default Skeleton;
