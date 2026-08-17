import type { ReactNode } from "react";

/** 图标组件参数：name 对应路径表中的图标键，size 控制像素尺寸。 */
type Props = { name: string; size?: number };

/**
 * 项目内置线性图标组件。
 * 所有图标共用同一 viewBox、描边和 currentColor，未知名称回退到网格图标而不让按钮空白。
 * @param name 路径表 key；未知 key 回退到 `grid` 占位图标。
 * @param size 图标宽高，默认 20 像素。
 */
export function Icon({ name, size = 20 }: Props) {
  // aria-hidden 表示图标只作装饰，可访问名称由外层按钮的文字或 aria-label 提供。
  // 统一 24x24 视口与 currentColor 描边，图标颜色自动跟随文字，主题切换无需换图。
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };  // 统一 24 视口与 currentColor，主题切换无需换图
  // 路径表集中管理图形，避免为每个小图标创建独立组件和额外模块请求。
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.66 3.58 3 8 3s8-1.34 8-3V5" /><path d="M4 12v7c0 1.66 3.58 3 8 3s8-1.34 8-3v-7" /></>,
    activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    x: <><path d="M6 6l12 12M18 6 6 18" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    lock: <><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    user: <><circle cx="12" cy="8" r="3.2" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3" /><path d="M21 4v16" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-14.6-3L4 10" /><path d="M4 5v5h5" /><path d="M4 13a8.1 8.1 0 0 0 14.6 3L20 14" /><path d="M20 19v-5h-5" /></>,
    download: <><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>,
    upload: <><path d="M12 21V9" /><path d="m7 14 5-5 5 5" /><path d="M5 3h14" /></>,
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></>,
    trash: <><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="m6 7 1 14h10l1-14" /><path d="M10 11v6M14 11v6" /></>,
    left: <path d="m15 18-6-6 6-6" />,
    right: <path d="m9 18 6-6-6-6" />,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M8 13h8M8 17h6" /></>,
    pie: <><path d="M12 3v9h9" /><path d="M19.1 15A8 8 0 1 1 9 4.9" /></>,
    chart: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    camera: <><path d="M14.5 4 16 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-3Z" /><circle cx="12" cy="13" r="4" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 15-5-5L5 20" /></>,
    sun: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.5M12 19.5V22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2 12h2.5M19.5 12H22M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" /></>,
    moon: <><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" /></>,
    link: <><path d="M9 15 15 9" /><path d="M11.5 6.5 13.5 4.5a3.6 3.6 0 0 1 5.1 5.1l-2 2a3.6 3.6 0 0 1-5.1 0" /><path d="M12.5 17.5 10.5 19.5a3.6 3.6 0 0 1-5.1-5.1l2-2a3.6 3.6 0 0 1 5.1 0" /></>,
  };
  return <svg {...common}>{paths[name] || paths.grid}</svg>; // 回退图标保证错误配置仍有稳定尺寸和视觉占位。
}
