/**
 * 侧边抽屉组件：复用 Dialog 的 useOverlayFocus 获得一致的焦点约束、
 * 背景滚动锁定和 Esc/遮罩关闭行为，只额外提供左右滑出方向。
 */
import { useId, useRef, type ReactNode } from "react";
import { useOverlayFocus } from "./Dialog";

/** Drawer 组件属性。 */
export interface DrawerProps {
  /** 是否打开；false 时不渲染任何 DOM。 */
  open: boolean;
  /** 抽屉标题，渲染为 h2 并作为 aria-labelledby 目标。 */
  title: string;
  /** 抽屉说明文字，存在时作为 aria-describedby 目标。 */
  description?: string;
  /** 滑出方向，默认右侧。 */
  side?: "left" | "right";
  /** 抽屉主体内容。 */
  children: ReactNode;
  /** 底部操作区。 */
  footer?: ReactNode;
  /** 请求关闭的回调；遮罩点击、关闭按钮与 Esc 触发。 */
  onClose: () => void;
}

/**
 * 侧边抽屉，复用 Dialog 的焦点约束与背景滚动锁定逻辑。
 * @param open 是否打开；false 时不渲染。
 * @param title 标题。
 * @param description 说明文字。
 * @param side 滑出方向，默认 right。
 * @param footer 底部操作区。
 * @param onClose 关闭回调。
 */
export function Drawer({ open, title, description, side = "right", children, footer, onClose }: DrawerProps) {
  // 抽屉与弹窗可能同屏存在，使用 useId 保证可访问性关联 ID 不冲突。
  const titleId = useId(); const descriptionId = useId(); const drawerRef = useRef<HTMLDivElement>(null);
  useOverlayFocus(open, onClose, drawerRef);
  if (!open) return null; // 不渲染关闭抽屉，避免移动端隐藏导航仍可被键盘聚焦。
  return <div className="fyt-overlay" data-side={side} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-drawer-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭抽屉" data-tooltip="关闭抽屉">×</button></div><div className="fyt-drawer-body">{children}</div>{footer ? <div className="fyt-drawer-foot">{footer}</div> : null}</div></div>;
}

export default Drawer;
