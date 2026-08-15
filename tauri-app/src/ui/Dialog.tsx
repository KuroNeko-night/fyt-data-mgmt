/** 无第三方依赖的可访问弹窗与覆盖层焦点管理。 */
import { useEffect, useId, useRef, type ReactNode } from "react";

/** 居中弹窗属性。 */
export interface DialogProps {
  /** 是否打开；false 时不渲染任何节点。 */
  open: boolean;
  /** 弹窗标题，作为无障碍名称关联到 role=dialog。 */
  title: string;
  /** 可选描述，存在时作为 aria-describedby 关联内容。 */
  description?: string;
  /** 弹窗主体内容。 */
  children: ReactNode;
  /** 可选底部操作区，通常放确认/取消按钮。 */
  footer?: ReactNode;
  /** 请求关闭的回调；Escape 和点击遮罩时也会触发。 */
  onClose: () => void;
}

/**
 * 弹层焦点管理 Hook：打开时保存原焦点、聚焦首个控件、限制 Tab 循环并支持 Escape 关闭。
 *
 * 监听器只在打开期间存在，关闭或卸载时解除并把焦点还给触发元素。焦点项每次按键重新
 * 查询，可适应弹层内容动态增加、禁用或删除控件。
 *
 * @param open 弹层是否打开；false 时不安装任何监听器。
 * @param onClose Escape 关闭时的回调，由调用方保证引用稳定或可接受重绑定。
 * @param dialogRef 弹层容器引用，焦点项从该容器内查询。
 * @returns 无返回值；副作用是全局 keydown 监听与焦点恢复。
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

/**
 * 渲染具备标题关联、模态语义、背景关闭和焦点圈定的居中弹窗。
 *
 * @param props.open 是否打开；为 false 时直接返回 null。
 * @param props.onClose 关闭回调；点击遮罩、Escape 或关闭按钮时触发。
 * @returns 带 role=dialog 和 aria-modal 的弹层，空态不渲染。
 */
export function Dialog({ open, title, description, children, footer, onClose }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId(); const descriptionId = useId();
  useOverlayFocus(open, onClose, dialogRef);
  if (!open) return null;
  return <div className="fyt-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-dialog-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭弹窗" data-tooltip="关闭弹窗">×</button></div><div className="fyt-dialog-body">{children}</div>{footer ? <div className="fyt-dialog-foot">{footer}</div> : null}</div></div>;
}

export default Dialog;
