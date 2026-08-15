/**
 * Web 首页首次使用引导。
 * 聚光区域绑定稳定的 `data-guide` 节点，窗口尺寸或任意滚动容器滚动时重新测量，
 * 不修改被介绍页面的交互状态。
 */
import { useCallback, useEffect, useState } from "react";
import { Icon } from "./icons";

/** 单个引导步骤：目标 `data-guide` 选择器以及弹窗文案。 */
type GuideStep = { target: string; title: string; text: string };

/** 引导步骤表；target 指向各壳层组件上稳定的 data-guide 锚点，不依赖易变的 DOM 结构。 */
const STEPS: GuideStep[] = [
  { target: '[data-guide="nav-workshop"]', title: "侧栏导航", text: "工作台、现场问题、业务模块、数据库与任务中心都从侧栏进入，常用入口一目了然。" },
  { target: '[data-guide="nav-features"]', title: "业务模块", text: "考勤、对账、采购、送货等业务都在「业务模块」中：上传文件、填写参数，系统自动处理并生成结果。" },
  { target: '[data-guide="topbar"]', title: "标题与主题", text: "顶部显示当前所在页面，右侧按钮可以随时切换浅色与深色主题。" },
  { target: '[data-guide="nav-tasks"]', title: "任务中心", text: "所有处理任务、结果文件下载与需要确认的任务都汇总在这里，处理过程全程可查。" },
]; 

/**
 * 首次使用引导浮层。
 * @param open 是否显示引导；关闭时卸载整个浮层。
 * @param onClose 用户跳过、完成或点击遮罩时的关闭回调。
 */
export function GuidedTour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<DOMRect | null>(null);
  // 索引夹紧到末步，防止异常状态导致取步越界。
  const step = STEPS[Math.min(index, STEPS.length - 1)];
  const last = index >= STEPS.length - 1;

  /** 测量当前目标；目标因权限隐藏时使用居中的对话框回退。 */
  const update = useCallback(() => {
    const element = document.querySelector(step.target);
    setBox(element ? element.getBoundingClientRect() : null);
  }, [step]);

  useEffect(() => {
    if (!open) return;
    // 每次重新打开都从第一步开始，避免上次关闭位置泄漏到新会话。
    setIndex(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // 打开时立即测量一次，并在窗口尺寸或任意内部滚动变化时重新定位。
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true); // 捕获阶段可接收内部滚动容器的非冒泡滚动事件。
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, update]);

  if (!open) return null;
  const below = box ? box.bottom + 190 < window.innerHeight : true; // 预留对话框近似高度，空间不足时放到目标上方。
  // 目标存在时贴住目标定位并夹在视口内；目标因权限隐藏时改用居中回退。
  const style: React.CSSProperties = box
    ? {
        left: Math.max(16, Math.min(box.left, window.innerWidth - 340)),
        top: below ? box.bottom + 14 : undefined,
        bottom: below ? undefined : window.innerHeight - box.top + 14,
      }
    : { left: "50%", transform: "translateX(-50%)", top: "40%" };

  return <div className="fyt-tour-layer" role="dialog" aria-label="使用引导">
    <div className="fyt-tour-shade" onClick={onClose} />
    {box ? <div className="fyt-tour-focus" style={{ left: box.left, top: box.top, width: box.width, height: box.height }} /> : null}
    <div className="fyt-tour-dialog" style={style}>
      <div className="fyt-tour-progress">{STEPS.map((_, i) => <i key={i} className={i <= index ? "active" : ""} />)}</div>
      <div className="fyt-tour-count">{index + 1} / {STEPS.length}</div>
      <h2>{step.title}</h2>
      <p>{step.text}</p>
      <div className="fyt-tour-actions">
        <button className="fyt-tour-skip" onClick={onClose}>跳过</button>
        <div>
          {index > 0 ? <button className="fyt-tour-back" onClick={() => setIndex((v) => v - 1)}>上一步</button> : null}
          <button className="fyt-action-primary fyt-tour-next" onClick={() => { if (last) onClose(); else setIndex((v) => v + 1); }}>{last ? "开始使用" : "下一步"} <Icon name="arrow" size={15} /></button>
        </div>
      </div>
    </div>
  </div>;
}
