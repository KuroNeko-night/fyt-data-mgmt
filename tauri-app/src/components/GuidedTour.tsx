/**
 * 根据当前页面已经渲染的真实 DOM 动态生成桌面端分步引导。
 *
 * 页面通过 `data-tour` 和既有业务卡片类名声明候选区域。本模块负责筛选可见节点、
 * 将目标滚动到视野中、计算聚光灯裁剪区域，并在引导对话框内维持键盘焦点。
 * 它不保存跨页面引导进度，也不会修改被介绍组件的状态。
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * 引导组件的受控属性。
 *
 * `open` 决定是否渲染；`refreshKey` 变化会驱动步骤重新采集；`reduceMotion`
 * 只控制滚动动画，不影响步骤生成与键盘焦点圈定。
 */
interface GuidedTourProps {
  open: boolean;
  pageKey: string;
  pageTitle: string;
  pageDescription: string;
  reduceMotion: boolean;
  onClose: () => void;
  refreshKey: string;
}

/** 单条引导步骤：持有真实 DOM 引用、客户文案与初始方位。 */
interface TourStep {
  key: string;
  element: HTMLElement;
  title: string;
  description: string;
  placement: "right" | "bottom" | "left";
}

// 空矩形既是初始占位，也是步骤切换期间隐藏旧聚光灯位置的明确状态。
const EMPTY_RECT = { left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 };
// 选择器顺序代表引导采集顺序；页面标题会始终作为第一步单独加入。
const CANDIDATE_SELECTOR = [
  '[data-tour="file-input"]',
  '[data-tour="parameter"]',
  '[data-tour="task-panel"]',
  '[data-tour="result-summary"]',
  ".fyt-tauri-home-section",
  ".fyt-tauri-home-note",
  ".fyt-option-card",
  ".fyt-tool-card",
  ".fyt-currency-result",
  ".fyt-text-workbench > .fyt-editor-panel",
  ".fyt-table-card",
  ".fyt-library-overview",
  ".fyt-template-list-panel",
  ".fyt-template-detail-panel",
  ".fyt-settings-card",
  ".fyt-about-card",
  ".fyt-workspace-card",
  ".fyt-run-strip",
  ".fyt-input-row",
  '[data-tour="home-overview"]',
  '[data-tour="home-actions"]',
  '[data-tour="home-recent-tasks"]',
  '[data-tour="home-notes"]',
].join(",");

/** 提取适合作为引导文案的可见文本，并折叠布局产生的连续空白。 */
function visibleText(element: Element | null) {
  return (element?.textContent || "").replace(/\s+/g, " ").trim();
}

/** 根据目标靠近视口哪一侧，为说明卡选择更不易遮挡目标的初始方位。 */
function placementFor(element: HTMLElement): TourStep["placement"] {
  const rect = element.getBoundingClientRect();
  if (rect.left < 300) return "right";
  if (rect.right > window.innerWidth - 300) return "left";
  return "bottom";
}

/**
 * 从候选节点的显式引导属性或可见标题中生成面向用户的说明。
 * 显式 `data-tour-*` 文案优先，可避免复杂卡片的全部文本被误当成标题或描述。
 */
function describeCandidate(element: HTMLElement) {
  const kind = element.dataset.tour || "";
  const heading = element.dataset.tourTitle
    || visibleText(element.querySelector("h2, h3, .fyt-field-heading strong, .fyt-table-toolbar strong, .fyt-panel-heading strong, label, strong"));
  const detail = element.dataset.tourDescription
    || visibleText(element.querySelector("p, small, .fyt-table-toolbar span, .fyt-panel-heading span"));

  const rules: Array<[(element: HTMLElement) => boolean, () => { title: string; description: string }]> = [
    [() => kind === "file-input", () => ({
      title: `放置：${heading || "业务文件"}`,
      description: `${detail || "选择这里要求的业务文件。"} 可点击“选择文件”，也可把文件直接拖入虚线区域。`,
    })],
    [() => kind === "parameter", () => ({
      title: `设置：${heading || "处理参数"}`,
      description: detail || "在这里选择工作表和需要使用的字段；不确定时保持自动识别即可。",
    })],
    [() => kind === "task-panel", () => ({
      title: `运行：${heading || "开始处理"}`,
      description: "输入准备完成后在这里开始处理。页面会显示进度，完成后可直接查看结果或打开保存位置。",
    })],
    [() => kind === "result-summary" || element.classList.contains("fyt-currency-result"), () => ({
      title: "查看处理结果",
      description: "处理数量、异常提示和结果文件会显示在这里，您可以直接复制内容或打开文件。",
    })],
    [() => element.classList.contains("fyt-option-card"), () => ({
      title: heading ? `设置：${heading}` : "选择处理方式",
      description: detail || "在这里选择处理模式并调整业务参数；不确定时可保留默认值。",
    })],
    [() => element.classList.contains("fyt-editor-panel"), () => {
      const isResult = heading.includes("结果");
      return {
        title: isResult ? "查看与复用文本结果" : "输入待处理文本",
        description: isResult ? "处理后的文本显示在这里，可复制，也可回填到左侧继续下一步处理。" : "在这里粘贴或输入原始文本，再从下方选择需要的处理动作。",
      };
    }],
    [() => element.classList.contains("fyt-tauri-home-section") || element.dataset.tour === "home-actions", () => ({ title: "选择常用业务", description: "这里汇总常用业务入口，点击任一项目即可进入对应功能。" })],
    [() => element.classList.contains("fyt-tauri-home-note") || element.dataset.tour === "home-notes", () => ({ title: "查看处理信息", description: "这里显示当前处理方式、资料归档和任务留痕情况，开始处理前可快速确认。" })],
    [() => element.classList.contains("fyt-table-card"), () => ({ title: heading || "查看与管理数据", description: detail || "这里集中展示当前页面的数据、状态与操作入口，可通过筛选或表格列定位需要的记录。" })],
    [() => element.classList.contains("fyt-settings-card"), () => ({ title: `配置：${heading || "系统选项"}`, description: detail || "这里管理这一组运行偏好；修改后在页面底部点击“保存设置”即可生效。" })],
    [() => element.classList.contains("fyt-template-list-panel"), () => ({ title: "选择模板", description: "左侧显示已保存的模板和版本，选择后可在右侧查看详细内容。" })],
    [() => element.classList.contains("fyt-template-detail-panel"), () => ({ title: "查看和调整模板", description: "右侧可以查看不同版本，并设置列名调整、删除列或默认值；保存后同类文件会沿用设置。" })],
  ];

  for (const [matches, build] of rules) {
    if (matches(element)) return build();
  }
  return {
    title: heading || "了解这个区域",
    description: detail || "这里提供当前功能的主要信息和操作入口。",
  };
}

/**
 * 扫描当前页面内容并生成稳定的引导步骤快照。
 *
 * 只采集当时具有布局尺寸的节点；嵌套在选项卡中的参数行由父卡片统一介绍，
 * 避免同一片区域重复聚光。返回值持有 DOM 引用，仅在本次打开的引导中使用。
 */
function collectTourSteps(pageKey: string, pageTitle: string, pageDescription: string) {
  const heading = document.querySelector<HTMLElement>('[data-tour="page-heading"]');
  const content = document.querySelector<HTMLElement>('[data-tour="page-content"]');
  if (!heading || !content) return [];

  const steps: TourStep[] = [{
    key: `${pageKey}:intro`,
    element: heading,
    title: `认识${pageTitle}`,
    description: pageDescription,
    placement: "bottom",
  }];
  const seen = new Set<HTMLElement>();
  const candidates = Array.from(content.querySelectorAll<HTMLElement>(CANDIDATE_SELECTOR));
  candidates.forEach((element, index) => {
    // 隐藏节点没有可靠的测量结果；重复节点和父卡已覆盖的参数行也不应形成独立步骤。
    if (seen.has(element) || element.offsetWidth === 0 || element.offsetHeight === 0) return;  // 隐藏节点和已覆盖节点不生成步骤
    if (element.dataset.tour === "parameter" && element.closest(".fyt-option-card")) return;  // 父卡片已统一介绍，避免参数行重复聚光
    if (element.classList.contains("fyt-currency-result") && !visibleText(element)) return;
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

/**
 * 计算说明卡位置，并把结果限制在视口四周的安全边距内。
 * 固定高度是定位阶段的保守估计，实际内容仍由 CSS 控制和滚动处理。
 */
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

/**
 * 渲染当前页面的聚光式操作引导。
 *
 * `refreshKey` 由外层在页面内容结构变化时更新，使步骤重新采集；`reduceMotion`
 * 只控制滚动动画，不改变步骤、焦点圈定或键盘操作能力。
 */
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
    // 等待本轮 React DOM 提交完成后再查询节点，避免采集到上一个页面尚未卸载的内容。
    const frame = window.requestAnimationFrame(() => {
      setStepIndex(0);
      setSteps(collectTourSteps(pageKey, pageTitle, pageDescription));  // 等待本轮 DOM 提交后再采集，避免拿到上一页内容
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, pageDescription, pageKey, pageTitle, refreshKey]);

  useLayoutEffect(() => {
    if (!open || !step) return;
    const target = step.element;
    const scrollContainer = target.closest<HTMLElement>(".fyt-tauri-content-scroll, .content-scroll");
    // 先清空旧矩形，防止平滑滚动期间聚光灯短暂指向上一步的位置。
    setTargetRect(EMPTY_RECT);
    target.scrollIntoView({ block: "center", inline: "nearest", behavior: reduceMotion ? "auto" : "smooth" });  // 先把目标滚到视野中央再计算聚光位置

    const updateTarget = () => {
      if (!target.isConnected) return;
      const rect = target.getBoundingClientRect();
      const bounds = scrollContainer?.getBoundingClientRect();
      // 聚光区域取目标与实际滚动视口的交集，避免遮罩“照亮”已被容器裁掉的部分。
      const left = Math.max(rect.left, bounds?.left ?? 0);  // 聚光区域取目标与滚动视口的交集
      const top = Math.max(rect.top, bounds?.top ?? 0);
      const right = Math.min(rect.right, bounds?.right ?? window.innerWidth);
      const bottom = Math.min(rect.bottom, bounds?.bottom ?? window.innerHeight);
      if (right <= left || bottom <= top) return;
      setTargetRect({ left, top, width: right - left, height: bottom - top, right, bottom });
    };
    const frame = window.requestAnimationFrame(updateTarget);
    // 平滑滚动没有统一的完成事件，延迟复测用于取得滚动基本稳定后的最终位置。
    const settleTimer = window.setTimeout(updateTarget, reduceMotion ? 40 : 360);
    // 表格加载、字体换行或卡片展开都可能改变尺寸，观察目标可保持聚光边框贴合。
    const observer = new ResizeObserver(updateTarget);
    observer.observe(target);
    target.addEventListener("transitionend", updateTarget);
    scrollContainer?.addEventListener("scroll", updateTarget, { passive: true }); // 监听器不拦截滚动，保持触控板与触摸操作流畅。
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
    // 每次切换步骤都把焦点送回对话框，屏幕阅读器和键盘用户无需寻找新的操作区域。
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
      // 在首尾元素之间循环 Tab，把焦点限制在 aria-modal 对话框内部。
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
    <div className="fyt-tour" role="presentation">
      <svg className="fyt-tour-shade" width="100%" height="100%" aria-hidden="true">
        <defs>
          <mask id="tour-spotlight-mask">
            <rect width="100%" height="100%" fill="white" />
            {/* 黑色圆角矩形从遮罩中扣除目标区域，周围仍由半透明背景覆盖。 */}
            <rect x={targetRect.left - padding} y={targetRect.top - padding} width={targetRect.width + padding * 2} height={targetRect.height + padding * 2} rx="18" fill="black" />
          </mask>
        </defs>
        <rect width="100%" height="100%" mask="url(#tour-spotlight-mask)" />
      </svg>
      <div className="fyt-tour-focus-ring" style={{ left: targetRect.left - padding, top: targetRect.top - padding, width: targetRect.width + padding * 2, height: targetRect.height + padding * 2 }} />
      <div ref={dialogRef} className={`fyt-tour-dialog placement-${step.placement}`} role="dialog" aria-modal="true" aria-labelledby="tour-title" style={dialogPosition}>
        <div className="fyt-tour-progress" aria-label={`引导进度 ${stepIndex + 1}/${steps.length}`}>
          {/* 已到达步骤保持高亮，用户可直观看到整体进度而不是只看到当前位置。 */}
          {steps.map((item, index) => <i key={item.key} className={index <= stepIndex ? "is-active" : ""} />)}
        </div>
        <span className="fyt-tour-count">{String(stepIndex + 1).padStart(2, "0")} / {String(steps.length).padStart(2, "0")}</span>
        <h2 id="tour-title">{step.title}</h2>
        <p>{step.description}</p>
        <div className="fyt-tour-actions">
          <button type="button" className="fyt-tour-skip" onClick={onClose}>结束本页引导</button>
          <div>
            <button type="button" className="fyt-button" data-variant="secondary" data-size="sm" disabled={stepIndex === 0} onClick={() => setStepIndex((value) => value - 1)}>上一步</button>
            <button type="button" className="fyt-button" data-variant="primary" data-size="sm" onClick={() => {
              if (stepIndex === steps.length - 1) onClose();
              else setStepIndex((value) => value + 1);
            }}>{stepIndex === steps.length - 1 ? "完成引导" : "下一步"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
