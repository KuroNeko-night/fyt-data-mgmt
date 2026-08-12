import { useId, useRef, type ReactNode } from "react";
import { useOverlayFocus } from "./Dialog";

export interface DrawerProps {
  open: boolean;
  title: string;
  description?: string;
  side?: "left" | "right";
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}

/** 侧边抽屉，复用 Dialog 的焦点约束与背景滚动锁定逻辑。 */
export function Drawer({ open, title, description, side = "right", children, footer, onClose }: DrawerProps) {
  const titleId = useId(); const descriptionId = useId(); const drawerRef = useRef<HTMLDivElement>(null);
  useOverlayFocus(open, onClose, drawerRef);
  if (!open) return null; // 不渲染关闭抽屉，避免移动端隐藏导航仍可被键盘聚焦。
  return <div className="fyt-overlay" data-side={side} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-drawer-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭抽屉" data-tooltip="关闭抽屉">×</button></div><div className="fyt-drawer-body">{children}</div>{footer ? <div className="fyt-drawer-foot">{footer}</div> : null}</div></div>;
}

export default Drawer;
