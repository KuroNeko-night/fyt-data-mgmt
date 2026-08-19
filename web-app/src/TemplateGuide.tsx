import { useEffect, useRef, useState } from "react";
import { guidanceFor } from "./businessGuidance";
import { Icon } from "./icons";

/**
 * 业务模板速览：把“应该上传什么、表格大概长什么样、会得到什么”放在同一处。
 * 组件只渲染静态说明，不读取文件，也不把示例值提交给服务端。
 * 展开状态由悬浮、焦点和点击固定三者共同决定：鼠标悬浮时跟随指针显示，
 * 键盘聚焦时保持可读，点击则用于触摸设备或需要停留阅读的固定展开。
 */
export function TemplateGuide({ featureKey, title }: { featureKey: string; title?: string }) {
  const guide = guidanceFor(featureKey, title);
  const template = guide.template;
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const open = hovered || focused || pinned;

  useEffect(() => {
    if (!open) return undefined;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setPinned(false);
      const active = document.activeElement;
      if (active instanceof HTMLElement && rootRef.current?.contains(active)) active.blur();  // 同时移出焦点，避免焦点态立刻把面板重新展开。
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  /** 取消点击固定；若焦点仍在面板内，先移出焦点防止焦点态立即重开。 */
  function unpin() {
    setPinned(false);
    const active = document.activeElement;
    if (active instanceof HTMLElement && rootRef.current?.contains(active)) active.blur();
  }

  /** 点击在“固定展开”和“取消固定”之间切换，不干扰悬浮与焦点展开。 */
  function togglePinned() {
    if (pinned) unpin();
    else setPinned(true);
  }

  return <div className="fyt-template-guide" ref={rootRef} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}>
    <button className="fyt-template-guide-trigger" type="button" aria-expanded={open} aria-controls={`template-guide-${featureKey}`} onClick={togglePinned}>
      <Icon name="file" size={15} />模板参考
    </button>
    <section className="fyt-template-guide-popover" id={`template-guide-${featureKey}`} role="dialog" aria-label={`${template.name}模板参考`} aria-hidden={!open} data-open={open ? "true" : undefined}>
      <header className="fyt-template-guide-head">
        <div>
          <div className="fyt-template-guide-kicker">输入模板示意</div>
          <h2>{template.name}</h2>
          <p>{template.description}</p>
        </div>
        <button className="fyt-template-guide-close" type="button" tabIndex={open ? 0 : -1} aria-label="关闭模板参考" onClick={unpin}><Icon name="x" size={15} /></button>
      </header>
      <div className="fyt-template-guide-table-wrap">
        <table className="fyt-template-guide-table">
          <thead><tr>{template.headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
          <tbody>{template.rows.map((values, rowIndex) => <tr key={rowIndex}>{template.headers.map((header, cellIndex) => <td key={`${header}-${cellIndex}`}>{values[cellIndex] || "—"}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <div className="fyt-template-guide-result"><strong>处理后</strong><span>{template.output}</span></div>
      <ul className="fyt-template-guide-tips">{template.tips.map((tip) => <li key={tip}>{tip}</li>)}</ul>
    </section>
  </div>;
}

export default TemplateGuide;
