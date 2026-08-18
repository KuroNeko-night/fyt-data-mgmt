/**
 * 模态弹窗组件与共享覆盖层焦点管理 Hook。
 * 覆盖层统一处理背景滚动锁定、初始聚焦、Esc 关闭、Tab 焦点循环和关闭后焦点还原，
 * 供 Dialog 与 Drawer 复用，保证弹层交互和可访问性行为一致。
 */
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Dialog 组件属性。 */
export interface DialogProps {
  /** 是否打开；false 时不渲染任何 DOM。 */
  open: boolean;
  /** 弹窗标题，同时用于无障碍名称。 */
  title: string;
  /** 弹窗说明文字，存在时关联为 aria-describedby。 */
  description?: string;
  /** 弹窗主体内容。 */
  children: ReactNode;
  /** 底部操作区，通常放取消/确认按钮。 */
  footer?: ReactNode;
  /** 弹窗宽度档位，默认 default。 */
  size?: "default" | "large";
  /** 请求关闭的回调；由遮罩点击、关闭按钮或 Esc 触发。 */
  onClose: () => void;
}

/**
 * 为弹窗和抽屉提供共同的覆盖层交互：锁定背景滚动、初始聚焦、Esc 关闭和 Tab 焦点循环。
 * 关闭时恢复原页面滚动样式及打开弹层前的焦点位置。
 * @param open 弹层是否打开；关闭时 effect 直接返回，不锁定也不监听键盘。
 * @param onClose 关闭回调，Esc 与遮罩点击会复用它。
 * @param dialogRef 弹层容器引用，用于查询可聚焦控件并执行焦点循环。
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
    document.body.style.overflow = "hidden";  // 打开弹层期间锁定背景滚动
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

/**
 * 带可访问标题、说明、焦点约束和背景点击关闭的通用模态弹窗。
 * @param open 是否打开；false 时不渲染，隐藏 DOM 不留在页面中。
 * @param title 标题，渲染为 h2 并作为 aria-labelledby 目标。
 * @param description 说明文字，存在时作为 aria-describedby 目标。
 * @param footer 底部操作区。
 * @param size 宽度档位。
 * @param onClose 关闭回调；遮罩点击、关闭按钮与 Esc 共用该回调。
 */
export function Dialog({ open, title, description, children, footer, size = "default", onClose }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // 用 useId 生成唯一后缀，保证同页多个弹窗的标题/描述关联互不冲突。
  const titleId = useId(); const descriptionId = useId();
  useOverlayFocus(open, onClose, dialogRef);
  if (!open) return null; // 关闭时不保留隐藏 DOM，避免隐藏控件仍参与焦点顺序。
  // 只有按下事件直接落在遮罩层本身才关闭，弹层内部的点击冒泡不会误触发关闭。
  const overlay = <div className="fyt-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="fyt-dialog" data-size={size} ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}><div className="fyt-dialog-head"><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button className="fyt-icon-button" type="button" onClick={onClose} aria-label="关闭弹窗" data-tooltip="关闭弹窗">×</button></div><div className="fyt-dialog-body">{children}</div>{footer ? <div className="fyt-dialog-foot">{footer}</div> : null}</div></div>;
  // 毛玻璃、transform 或 overflow 祖先可能改变 fixed 的包含块；Portal 让所有弹窗脱离业务卡片层叠上下文。
  return typeof document === "undefined" ? overlay : createPortal(overlay, document.body);
}

export default Dialog;
