import { useEffect, useId, useRef, type ReactNode } from "react";

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "default" | "large";
  onClose: () => void;
}

/**
 * 为弹窗和抽屉提供共同的覆盖层交互：锁定背景滚动、初始聚焦、Esc 关闭和 Tab 焦点循环。
 * 关闭时恢复原页面滚动样式及打开弹层前的焦点位置。
 */
export function useOverlayFocus(open: boolean, onClose: () => void, dialogRef: React.RefObject<HTMLDivElement | null>) {
  // 记录触发弹层的控件，关闭后恢复焦点，键盘用户可继续原来的操作位置。
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // 保存行内样式而不是假定默认值，避免覆盖其他页面设置的滚动策略。
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    // 隐藏 body 滚动条后补同等右内边距，防止页面内容横向跳动。
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    // 优先聚焦第一个可交互控件；若弹层只有说明文字则保持当前焦点。
    const focusable = dialogRef.current?.querySelector<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])");
    focusable?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      // 每次按 Tab 都重新查询，确保异步出现或禁用的按钮不会破坏焦点循环。
      const items = [...dialogRef.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])")].filter((item) => !item.hasAttribute("disabled"));
      if (items.length === 0) return;
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
      returnFocus.current?.focus();
    };
  }, [dialogRef, onClose, open]);
}

/** 带可访问标题、说明、焦点约束和背景点击关闭的通用模态弹窗。 */
export function Dialog({ open, title, description, children, footer, size = "default", onClose }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId(); const descriptionId = useId();
  useOverlayFocus(open, onClose, dialogRef);
  if (!open) return null; // 关闭时不保留隐藏 DOM，避免隐藏控件仍参与焦点顺序。
  return <div className="fyt-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-dialog" data-size={size} ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-dialog-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭弹窗" data-tooltip="关闭弹窗">×</button></div><div className="fyt-dialog-body">{children}</div>{footer ? <div className="fyt-dialog-foot">{footer}</div> : null}</div></div>;
}

export default Dialog;
