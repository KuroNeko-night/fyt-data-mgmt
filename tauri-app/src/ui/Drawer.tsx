/** 复用弹窗焦点规则的左右侧抽屉组件。 */
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

/** 渲染带模态语义、背景关闭、标题关联和可选底部操作区的侧抽屉。 */
export function Drawer({ open, title, description, side = "right", children, footer, onClose }: DrawerProps) {
  const titleId = useId(); const descriptionId = useId(); const drawerRef = useRef<HTMLDivElement>(null);
  useOverlayFocus(open, onClose, drawerRef);
  if (!open) return null;
  return <div className="fyt-overlay" data-side={side} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-drawer-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭抽屉" data-tooltip="关闭抽屉">×</button></div><div className="fyt-drawer-body">{children}</div>{footer ? <div className="fyt-drawer-foot">{footer}</div> : null}</div></div>;
}

export default Drawer;
