import { useEffect, useLayoutEffect, useRef, useState } from "react";

interface GuidedTourProps {
  open: boolean;
  pageKey: string;
  pageTitle: string;
  pageDescription: string;
  reduceMotion: boolean;
  onClose: () => void;
  refreshKey: string;
}

interface TourStep {
  key: string;
  element: HTMLElement;
  title: string;
  description: string;
  placement: "right" | "bottom" | "left";
}

const EMPTY_RECT = { left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 };
const CANDIDATE_SELECTOR = [
  '[data-tour="file-input"]',
  '[data-tour="parameter"]',
  '[data-tour="task-panel"]',
  '[data-tour="result-summary"]',
  ".hero-card",
  ".shortcut-grid",
  ".info-band",
  ".option-card",
  ".tool-card",
  ".currency-result",
  ".text-workbench > .editor-panel",
  ".table-card",
  ".library-overview",
  ".template-list-panel",
  ".template-detail-panel",
  ".settings-card",
  ".about-card",
].join(",");

function visibleText(element: Element | null) {
  return (element?.textContent || "").replace(/\s+/g, " ").trim();
}

function placementFor(element: HTMLElement): TourStep["placement"] {
  const rect = element.getBoundingClientRect();
  if (rect.left < 300) return "right";
  if (rect.right > window.innerWidth - 300) return "left";
  return "bottom";
}

function describeCandidate(element: HTMLElement) {
  const kind = element.dataset.tour || "";
  const heading = element.dataset.tourTitle
    || visibleText(element.querySelector("h2, h3, .field-heading strong, .table-toolbar strong, .panel-heading strong, label, strong"));
  const detail = element.dataset.tourDescription
    || visibleText(element.querySelector("p, small, .table-toolbar span, .panel-heading span"));

  if (kind === "file-input") {
    return {
      title: `放置：${heading || "业务文件"}`,
      description: `${detail || "选择这里要求的业务文件。"} 可点击“选择文件”，也可把文件直接拖入虚线区域。`,
    };
  }
  if (kind === "parameter") {
    return {
      title: `设置：${heading || "处理参数"}`,
      description: detail || "在这里指定当前文件的工作表、字段或处理口径；不确定时可保留自动识别或默认值。",
    };
  }
  if (kind === "task-panel") {
    return {
      title: `运行：${heading || "开始处理"}`,
      description: "输入准备完成后在这里启动任务。状态点、进度条和折叠日志会持续反馈处理过程；完成后可直接打开结果或输出目录。",
    };
  }
  if (kind === "result-summary" || element.classList.contains("currency-result")) {
    return {
      title: "查看处理结果",
      description: "完成后的数量、可信度、异常提示和结果位置会集中显示在这里；需要继续使用时可复制内容或打开生成文件。",
    };
  }
  if (element.classList.contains("option-card")) {
    return {
      title: heading ? `设置：${heading}` : "选择处理方式",
      description: detail || "在这里选择处理模式并调整业务参数。首次使用可先保留默认值，再按结果逐步优化。",
    };
  }
  if (element.classList.contains("editor-panel")) {
    const isResult = heading.includes("结果");
    return {
      title: isResult ? "查看与复用文本结果" : "输入待处理文本",
      description: isResult ? "处理后的文本显示在这里，可复制，也可回填到左侧继续下一步处理。" : "在这里粘贴或输入原始文本，再从下方选择需要的处理动作。",
    };
  }
  if (element.classList.contains("shortcut-grid")) {
    return { title: "选择常用业务", description: "这里汇总高频业务入口，点击任一项目即可进入对应功能，并获得该功能自己的使用引导。" };
  }
  if (element.classList.contains("info-band")) {
    return { title: "确认运行环境", description: "这里显示 Python 核心、运行环境与输出约定，开始处理前可快速确认系统状态。" };
  }
  if (element.classList.contains("table-card")) {
    return { title: heading || "查看与管理数据", description: detail || "这里集中展示当前页面的数据、状态与操作入口，可通过筛选或表格列定位需要的记录。" };
  }
  if (element.classList.contains("settings-card")) {
    return { title: `配置：${heading || "系统选项"}`, description: detail || "这里管理这一组运行偏好；修改后在页面底部点击“保存设置”使其同步到 Python 核心。" };
  }
  if (element.classList.contains("template-list-panel")) {
    return { title: "选择模板族", description: "左侧列出已保存的模板族和版本数量，先选择一个模板，再到右侧查看结构变化。" };
  }
  if (element.classList.contains("template-detail-panel")) {
    return { title: "查看版本并维护迁移规则", description: "右侧展示模板版本、字段差异和迁移规则；保存规则后，同类新表可自动适配结构变化。" };
  }
  return {
    title: heading || "了解这个区域",
    description: detail || "这里提供当前功能的主要信息和操作入口。",
  };
}

function collectTourSteps(pageKey: string, pageTitle: string, pageDescription: string) {
  const heading = document.querySelector<HTMLElement>('[data-tour="page-heading"]');
  const content = document.querySelector<HTMLElement>('[data-tour="page-content"]');
  if (!heading || !content) return [];

  const steps: TourStep[] = [{
    key: `${pageKey}:intro`,
    element: heading,
    title: `认识${pageTitle}`,
    description: `${pageDescription}。下面会按页面真实布局说明输入放在哪里、如何设置，以及去哪里查看处理结果。`,
    placement: "bottom",
  }];
  const seen = new Set<HTMLElement>();
  const candidates = Array.from(content.querySelectorAll<HTMLElement>(CANDIDATE_SELECTOR));
  candidates.forEach((element, index) => {
    if (seen.has(element) || element.offsetWidth === 0 || element.offsetHeight === 0) return;
    if (element.dataset.tour === "parameter" && element.closest(".option-card")) return;
    if (element.classList.contains("currency-result") && !visibleText(element)) return;
    seen.add(element);
    const copy = describeCandidate(element);
    steps.push({
      key: `${pageKey}:${element.dataset.tour || element.className}:${index}`,
      element,
      title: copy.title,
      description: copy.description,
      placement: placementFor(element),
    });
  });
  return steps;
}

function getDialogPosition(rect: typeof EMPTY_RECT, placement: TourStep["placement"]) {
  const width = Math.min(372, window.innerWidth - 32);
  const height = 238;
  const gap = 20;
  let left = rect.left;
  let top = rect.bottom + gap;
  if (placement === "right") {
    left = rect.right + gap;
    top = rect.top + Math.min(42, Math.max(0, rect.height / 5));
  } else if (placement === "left") {
    left = rect.left - width - gap;
    top = rect.top + Math.min(42, Math.max(0, rect.height / 5));
  }
  return {
    left: Math.max(16, Math.min(left, window.innerWidth - width - 16)),
    top: Math.max(16, Math.min(top, window.innerHeight - height - 16)),
    width,
  };
}

export default function GuidedTour({
  open, pageKey, pageTitle, pageDescription, reduceMotion, onClose, refreshKey,
}: GuidedTourProps) {
  const [steps, setSteps] = useState<TourStep[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState(EMPTY_RECT);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const step = steps[stepIndex];

  useLayoutEffect(() => {
    if (!open) {
      setSteps([]);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      setStepIndex(0);
      setSteps(collectTourSteps(pageKey, pageTitle, pageDescription));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, pageDescription, pageKey, pageTitle, refreshKey]);

  useLayoutEffect(() => {
    if (!open || !step) return;
    const target = step.element;
    const scrollContainer = target.closest<HTMLElement>(".content-scroll");
    setTargetRect(EMPTY_RECT);
    target.scrollIntoView({ block: "center", inline: "nearest", behavior: reduceMotion ? "auto" : "smooth" });

    const updateTarget = () => {
      if (!target.isConnected) return;
      const rect = target.getBoundingClientRect();
      const bounds = scrollContainer?.getBoundingClientRect();
      const left = Math.max(rect.left, bounds?.left ?? 0);
      const top = Math.max(rect.top, bounds?.top ?? 0);
      const right = Math.min(rect.right, bounds?.right ?? window.innerWidth);
      const bottom = Math.min(rect.bottom, bounds?.bottom ?? window.innerHeight);
      if (right <= left || bottom <= top) return;
      setTargetRect({ left, top, width: right - left, height: bottom - top, right, bottom });
    };
    const frame = window.requestAnimationFrame(updateTarget);
    const settleTimer = window.setTimeout(updateTarget, reduceMotion ? 40 : 360);
    const observer = new ResizeObserver(updateTarget);
    observer.observe(target);
    target.addEventListener("transitionend", updateTarget);
    scrollContainer?.addEventListener("scroll", updateTarget, { passive: true });
    window.addEventListener("resize", updateTarget);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      observer.disconnect();
      target.removeEventListener("transitionend", updateTarget);
      scrollContainer?.removeEventListener("scroll", updateTarget);
      window.removeEventListener("resize", updateTarget);
    };
  }, [open, reduceMotion, step]);

  useEffect(() => {
    if (!open || !step) return;
    const dialog = dialogRef.current;
    const focusable = dialog?.querySelectorAll<HTMLElement>('button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])');
    focusable?.[0]?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open, step]);

  if (!open || !step) return null;
  const padding = 8;
  const dialogPosition = getDialogPosition(targetRect, step.placement);

  return (
    <div className="guided-tour" role="presentation">
      <svg className="tour-shade" width="100%" height="100%" aria-hidden="true">
        <defs>
          <mask id="tour-spotlight-mask">
            <rect width="100%" height="100%" fill="white" />
            <rect x={targetRect.left - padding} y={targetRect.top - padding} width={targetRect.width + padding * 2} height={targetRect.height + padding * 2} rx="18" fill="black" />
          </mask>
        </defs>
        <rect width="100%" height="100%" mask="url(#tour-spotlight-mask)" />
      </svg>
      <div className="tour-focus-ring" style={{ left: targetRect.left - padding, top: targetRect.top - padding, width: targetRect.width + padding * 2, height: targetRect.height + padding * 2 }} />
      <div ref={dialogRef} className={`tour-dialog placement-${step.placement}`} role="dialog" aria-modal="true" aria-labelledby="tour-title" style={dialogPosition}>
        <div className="tour-progress" aria-label={`引导进度 ${stepIndex + 1}/${steps.length}`}>
          {steps.map((item, index) => <i key={item.key} className={index <= stepIndex ? "active" : ""} />)}
        </div>
        <span className="tour-count">{String(stepIndex + 1).padStart(2, "0")} / {String(steps.length).padStart(2, "0")}</span>
        <h2 id="tour-title">{step.title}</h2>
        <p>{step.description}</p>
        <div className="tour-actions">
          <button type="button" className="tour-skip" onClick={onClose}>结束本页引导</button>
          <div>
            <button type="button" className="secondary-button" disabled={stepIndex === 0} onClick={() => setStepIndex((value) => value - 1)}>上一步</button>
            <button type="button" className="primary-button" onClick={() => {
              if (stepIndex === steps.length - 1) onClose();
              else setStepIndex((value) => value + 1);
            }}>{stepIndex === steps.length - 1 ? "完成引导" : "下一步"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
