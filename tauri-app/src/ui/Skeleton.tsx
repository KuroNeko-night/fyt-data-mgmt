/** 不向辅助技术暴露内容的加载骨架占位。 */
export interface SkeletonProps {
  variant?: "line" | "title" | "rect";
  width?: string;
  className?: string;
}

/** 变体只控制视觉比例，可选宽度通过内联样式覆盖令牌默认值。 */
export function Skeleton({ variant = "line", width, className = "" }: SkeletonProps) {
  return <span className={`fyt-skeleton ${className}`.trim()} data-variant={variant} style={width ? { width } : undefined} aria-hidden="true" />;
}

export default Skeleton;
