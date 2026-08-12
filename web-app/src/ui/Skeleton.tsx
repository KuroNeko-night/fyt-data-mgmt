export interface SkeletonProps {
  variant?: "line" | "title" | "rect";
  width?: string;
  className?: string;
}

/** 纯装饰加载骨架；从辅助技术中隐藏，实际加载状态由外层区域说明。 */
export function Skeleton({ variant = "line", width, className = "" }: SkeletonProps) {
  return <span className={`fyt-skeleton ${className}`.trim()} data-variant={variant} style={width ? { width } : undefined} aria-hidden="true" />;
}

export default Skeleton;
