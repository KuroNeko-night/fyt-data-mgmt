/** 无第三方依赖的可访问弹窗与覆盖层焦点管理。 */
import { useEffect, useId, useRef, type ReactNode } from "react";

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}

/**
 * 弹层打开时保存原焦点、聚焦首个控件、限制 Tab 循环并支持 Escape 关闭。
 *
 * 监听器只在打开期间存在，关闭或卸载时解除并把焦点还给触发元素。焦点项每次按键重新
 * 查询，可适应弹层内容动态增加、禁用或删除控件。
 */
export function useOverlayFocus(open: boolean, onClose: () => void, dialogRef: React.RefObject<HTMLDivElement | null>) {
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; // 关闭后恢复用户原操作位置。
    const focusable = dialogRef.current?.querySelector<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])");
    focusable?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const items = [...dialogRef.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])")].filter((item) => !item.hasAttribute("disabled")); // 动态内容要求按当前 DOM 重算焦点顺序。
      if (items.length === 0) return;
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => { document.removeEventListener("keydown", handleKeyDown); returnFocus.current?.focus(); };
  }, [dialogRef, onClose, open]);
}

/** 渲染具备标题关联、模态语义、背景关闭和焦点圈定的居中弹窗。 */
export function Dialog({ open, title, description, children, footer, onClose }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId(); const descriptionId = useId();
  useOverlayFocus(open, onClose, dialogRef);
  if (!open) return null;
  return <div className="fyt-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-dialog-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭弹窗" data-tooltip="关闭弹窗">×</button></div><div className="fyt-dialog-body">{children}</div>{footer ? <div className="fyt-dialog-foot">{footer}</div> : null}</div></div>;
}

export default Dialog;
