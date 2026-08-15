/** 复用弹窗焦点规则的左右侧抽屉组件。 */
import { useId, useRef, type ReactNode } from "react";
import { useOverlayFocus } from "./Dialog";

/** 左右侧抽屉属性：复用弹窗焦点规则与遮罩交互。 */
export interface DrawerProps {
  /** 是否打开；false 时不渲染任何节点。 */
  open: boolean;
  /** 抽屉标题，关联到 role=dialog 的无障碍名称。 */
  title: string;
  /** 可选描述，存在时作为 aria-describedby 关联内容。 */
  description?: string;
  /** 抽屉从哪一侧滑出，默认右侧。 */
  side?: "left" | "right";
  /** 抽屉主体内容。 */
  children: ReactNode;
  /** 可选底部操作区。 */
  footer?: ReactNode;
  /** 关闭回调；Escape、点击遮罩或关闭按钮时触发。 */
  onClose: () => void;
}

/**
 * 渲染带模态语义、背景关闭、标题关联和可选底部操作区的侧抽屉。
 *
 * @param props.side 决定滑出方向与遮罩 data-side 标记。
 * @param props.onClose 关闭回调；遮罩点击和 Escape 复用 Dialog 的焦点规则。
 * @returns 带 role=dialog 和 aria-modal 的侧抽屉，关闭时返回 null。
 */
export function Drawer({ open, title, description, side = "right", children, footer, onClose }: DrawerProps) {
  const titleId = useId(); const descriptionId = useId(); const drawerRef = useRef<HTMLDivElement>(null);
  useOverlayFocus(open, onClose, drawerRef);
  if (!open) return null;
  return <div className="fyt-overlay" data-side={side} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-drawer-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭抽屉" data-tooltip="关闭抽屉">×</button></div><div className="fyt-drawer-body">{children}</div>{footer ? <div className="fyt-drawer-foot">{footer}</div> : null}</div></div>;
}

export default Drawer;
