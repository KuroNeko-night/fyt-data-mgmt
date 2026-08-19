import { useEffect, useMemo, useState } from "react";
import { listJobs, type Feature, type UserRole, type WebJob } from "./api";
import { WORKFLOW_DEFINITIONS, type WorkflowDefinition, type WorkflowStep } from "./businessGuidance";
import { Icon } from "./icons";
import Button from "./ui/Button";
import PageHeader from "./ui/PageHeader";
import Surface from "./ui/Surface";

/**
 * 智能工作流中心：把已有业务模块按依赖顺序串联成推荐路径。
 *
 * 页面只负责路径选择、步骤导航和当前账号的本地进度记录，不调用业务算法；
 * 真实处理仍进入对应业务页面执行。步骤顺序仅作建议，用户可自行勾选或取消。
 */

/** 每个账号、每条路径保存的已完成步骤键列表。 */
type ProgressMap = Record<string, string[]>;

/** 从工作流进入业务页时留下的待确认标记，用于返回后识别本次处理是否完成。 */
type PendingLaunch = {
  workflowKey: string;
  featureKey: string;
  openedAt: string;
};

/** 进度、选中路径和待确认标记都按账号隔离，避免共用浏览器时互相串号。 */
function progressKey(userId: number) {
  return `fyt-workflow-progress-v1:${userId}`;
}

function selectedKey(userId: number) {
  return `fyt-workflow-selected-v1:${userId}`;
}

function pendingKey(userId: number) {
  return `fyt-workflow-pending-v1:${userId}`;
}

/** 读取本地进度时过滤损坏或非字符串值，保证渲染只拿到合法步骤键。 */
function readProgress(userId: number): ProgressMap {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(progressKey(userId)) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    const result: ProgressMap = {};
    Object.entries(raw as Record<string, unknown>).forEach(([key, value]) => {
      if (!Array.isArray(value)) return;
      const steps = [...new Set(value.filter((item): item is string => typeof item === "string"))];  // 去重同时丢弃脏值
      if (steps.length) result[key] = steps;
    });
    return result;
  } catch {
    return {};
  }
}

/** 选中路径必须仍然存在于定义中，旧值或损坏值安全回退到第一条路径。 */
function readSelectedWorkflow(userId: number) {
  const value = localStorage.getItem(selectedKey(userId)) || "";
  return WORKFLOW_DEFINITIONS.some((item) => item.key === value) ? value : WORKFLOW_DEFINITIONS[0].key;
}

function readPendingLaunch(userId: number): PendingLaunch | null {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(pendingKey(userId)) || "null");
    if (!raw || typeof raw !== "object") return null;
    const candidate = raw as Record<string, unknown>;
    if (typeof candidate.workflowKey !== "string" || typeof candidate.featureKey !== "string" || typeof candidate.openedAt !== "string") return null;
    return { workflowKey: candidate.workflowKey, featureKey: candidate.featureKey, openedAt: candidate.openedAt };
  } catch {
    return null;
  }
}

function writePendingLaunch(userId: number, launch: PendingLaunch) {
  localStorage.setItem(pendingKey(userId), JSON.stringify(launch));
}

function clearPendingLaunch(userId: number) {
  localStorage.removeItem(pendingKey(userId));
}

/** 业务步骤是否对当前账号可用：通用模块看服务端目录，专用页面按角色判断。 */
function stepAvailable(features: Feature[], userRole: UserRole, step: WorkflowStep) {
  if (step.route === "workshop") return true;
  if (step.route === "daily-report") return userRole === "admin";
  return features.some((feature) => feature.key === step.featureKey);
}

/** 只有真正执行完成的正式任务才可自动勾选；待复核的分析快照不算完成。 */
function isFinalCompletion(job: WebJob) {
  return job.status === "completed" && !job.review_pending;
}

/** 将任务动作归一化回业务键：web.arrival 与 attendance.run 都对应各自功能。 */
function jobMatchesFeature(job: WebJob, featureKey: string) {
  return job.action === `web.${featureKey}` || job.action.startsWith(`${featureKey}.`);
}

/** 服务端与浏览器时间戳的小数精度可能不同，统一截取到秒再比较。 */
function atOrAfter(jobTime: string, openedAt: string) {
  return jobTime.slice(0, 19) >= openedAt.slice(0, 19);
}

function addCompletedStep(current: ProgressMap, workflowKey: string, featureKey: string): ProgressMap {
  const steps = new Set(current[workflowKey] || []);
  steps.add(featureKey);
  return { ...current, [workflowKey]: [...steps] };
}

function toggleCompletedStep(current: ProgressMap, workflowKey: string, featureKey: string): ProgressMap {
  const steps = new Set(current[workflowKey] || []);
  if (steps.has(featureKey)) steps.delete(featureKey);
  else steps.add(featureKey);
  return { ...current, [workflowKey]: [...steps] };
}

function workflowStepKeys(workflow: WorkflowDefinition, features: Feature[], userRole: UserRole) {
  return workflow.steps.filter((step) => stepAvailable(features, userRole, step)).map((step) => step.featureKey);
}

/** 进度只按当前账号可用步骤计算，无权限步骤既不拉低百分比，也不伪装成可完成。 */
function workflowProgress(completed: ReadonlySet<string>, availableKeys: string[]) {
  const done = availableKeys.filter((key) => completed.has(key)).length;
  return { done, total: availableKeys.length, percent: availableKeys.length ? Math.round((done / availableKeys.length) * 100) : 0 };
}

/**
 * 智能工作流页面：展示推荐路径、当前账号进度和步骤入口。
 * 从工作流打开通用业务并完成正式任务后，返回本页会依据待确认标记自动勾选；
 * 专用页面和未识别到的处理仍可由用户手动确认。
 */
export function WorkflowCenterPage({ features, userId, userRole, onOpen }: { features: Feature[]; userId: number; userRole: UserRole; onOpen: (step: WorkflowStep) => void }) {
  const [selectedKeyState, setSelectedKeyState] = useState(() => readSelectedWorkflow(userId));
  const [progress, setProgress] = useState<ProgressMap>(() => readProgress(userId));
  const [autoNotice, setAutoNotice] = useState("");
  const workflow = useMemo(() => WORKFLOW_DEFINITIONS.find((item) => item.key === selectedKeyState) || WORKFLOW_DEFINITIONS[0], [selectedKeyState]);
  const availableKeys = useMemo(() => workflowStepKeys(workflow, features, userRole), [workflow, features, userRole]);
  const completed = useMemo(() => new Set(progress[workflow.key] || []), [progress, workflow.key]);
  const progressInfo = workflowProgress(completed, availableKeys);
  const nextStep = workflow.steps.find((step) => !completed.has(step.featureKey) && stepAvailable(features, userRole, step));
  const allDone = availableKeys.length > 0 && availableKeys.every((key) => completed.has(key));
  const allStepsAvailable = progressInfo.total === workflow.steps.length;

  useEffect(() => {
    localStorage.setItem(progressKey(userId), JSON.stringify(progress));
  }, [progress, userId]);

  useEffect(() => {
    localStorage.setItem(selectedKey(userId), workflow.key);
  }, [workflow.key, userId]);

  useEffect(() => {
    const pending = readPendingLaunch(userId);
    if (!pending) return;
    let active = true;
    // 返回智能工作流时查询任务中心，只认“本次打开之后创建并最终完成”的正式任务。
    void listJobs().then(({ jobs }) => {
      if (!active) return;
      const finished = jobs.find((job) => isFinalCompletion(job) && jobMatchesFeature(job, pending.featureKey) && atOrAfter(job.created_at, pending.openedAt) && atOrAfter(job.updated_at, pending.openedAt));
      if (!finished) return;
      const definition = WORKFLOW_DEFINITIONS.find((item) => item.key === pending.workflowKey);
      const step = definition?.steps.find((item) => item.featureKey === pending.featureKey);
      setProgress((current) => addCompletedStep(current, pending.workflowKey, pending.featureKey));
      setAutoNotice(step ? `已检测到本次「${step.title}」处理完成，步骤已自动勾选。` : "已检测到本次业务处理完成，步骤已自动勾选。");
      clearPendingLaunch(userId);
    }).catch(() => undefined);  // 任务中心读取失败不阻塞页面，用户仍可手动确认。
    return () => { active = false; };
  }, [userId]);

  /** 进入具体业务页前记录来源，完成正式任务后返回本页即可自动勾选。 */
  function openStep(step: WorkflowStep) {
    if (!stepAvailable(features, userRole, step)) return;
    if (!step.route && features.some((feature) => feature.key === step.featureKey)) {
      writePendingLaunch(userId, { workflowKey: workflow.key, featureKey: step.featureKey, openedAt: new Date().toISOString() });
    }
    onOpen(step);
  }

  /** 手动确认或取消步骤；若存在同一来源的待确认标记则同步清除，避免以后重复自动勾选。 */
  function toggleDone(featureKey: string) {
    setProgress((current) => toggleCompletedStep(current, workflow.key, featureKey));
    setAutoNotice("");
    const pending = readPendingLaunch(userId);
    if (pending?.workflowKey === workflow.key && pending.featureKey === featureKey) clearPendingLaunch(userId);
  }

  function resetWorkflow() {
    if (!window.confirm(`确定重置「${workflow.title}」的全部步骤吗？`)) return;
    setProgress((current) => ({ ...current, [workflow.key]: [] }));
    setAutoNotice("");
    const pending = readPendingLaunch(userId);
    if (pending?.workflowKey === workflow.key) clearPendingLaunch(userId);
  }

  function selectWorkflow(key: string) {
    setSelectedKeyState(key);
    setAutoNotice("");
  }

  return <div className="fyt-workflow-page">
    <PageHeader eyebrow="流程助手" title="智能工作流" description="按照业务依赖顺序准备资料、处理文件并完成复核；从工作流进入业务页完成的正式任务，返回后会自动勾选对应步骤。" actions={<Button variant="secondary" size="sm" type="button" onClick={resetWorkflow}><Icon name="refresh" size={15} />重置当前进度</Button>} />
    <div className="fyt-workflow-layout">
      <aside className="fyt-workflow-catalog" aria-label="工作流列表">
        <div className="fyt-workflow-catalog-head"><span>推荐路径</span><strong>{WORKFLOW_DEFINITIONS.length} 条</strong></div>
        {WORKFLOW_DEFINITIONS.map((item) => {
          const itemKeys = workflowStepKeys(item, features, userRole);
          const itemProgress = workflowProgress(new Set(progress[item.key] || []), itemKeys);
          return <button key={item.key} type="button" className="fyt-workflow-catalog-item" data-selected={item.key === workflow.key ? "true" : undefined} data-complete={itemProgress.percent === 100 ? "true" : undefined} onClick={() => selectWorkflow(item.key)}>
            <span className="fyt-workflow-catalog-icon"><Icon name="route" size={17} /></span>
            <span><strong>{item.title}</strong><small>{item.audience}</small><i><b style={{ width: `${itemProgress.percent}%` }} /></i></span>
            <em>{itemProgress.percent}%</em>
          </button>;
        })}
      </aside>
      <main className="fyt-workflow-main">
        <Surface className="fyt-workflow-intro">
          <div><span className="fyt-workflow-kicker">当前路径</span><h2>{workflow.title}</h2><p>{workflow.description}</p></div>
          <div className="fyt-workflow-intro-progress"><strong>{progressInfo.percent}%</strong><span>已完成 {progressInfo.done}/{progressInfo.total} 步</span><i><b style={{ width: `${progressInfo.percent}%` }} /></i></div>
        </Surface>
        {autoNotice ? <div className="fyt-workflow-auto-notice" role="status"><Icon name="check" size={16} /><span>{autoNotice}</span></div> : null}
        {allDone ? <div className="fyt-workflow-complete" role="status"><Icon name="check" size={20} /><div><strong>{allStepsAvailable ? "当前路径已全部完成" : "当前账号可完成的步骤已全部完成"}</strong><span>可以开始下一轮，或选择其他推荐路径继续处理。</span></div><Button variant="ghost" size="sm" type="button" onClick={resetWorkflow}>重新开始</Button></div> : null}
        <section className="fyt-workflow-steps" aria-label={`${workflow.title}步骤`}>
          {workflow.steps.map((step, index) => {
            const available = stepAvailable(features, userRole, step);
            const done = completed.has(step.featureKey);
            const current = nextStep?.featureKey === step.featureKey;
            return <article className="fyt-workflow-step-card" data-current={current ? "true" : undefined} data-done={done ? "true" : undefined} data-unavailable={!available ? "true" : undefined} aria-current={current ? "step" : undefined} key={step.featureKey}>
              <div className="fyt-workflow-step-number">{done ? <Icon name="check" size={17} /> : String(index + 1).padStart(2, "0")}</div>
              <div className="fyt-workflow-step-copy"><div className="fyt-workflow-step-meta"><span>{done ? "已完成" : current ? "建议先做" : available ? `第 ${index + 1} 步` : "当前账号不可用"}</span>{!available && !done ? <em>当前账号不可用</em> : null}</div><h3>{step.title}</h3><p>{step.description}</p><small><Icon name="file" size={14} />输入示意：{step.input}</small></div>
              <div className="fyt-workflow-step-actions"><Button variant={current ? "primary" : "secondary"} size="sm" type="button" disabled={!available} onClick={() => openStep(step)}>{available ? "开始处理" : "无权限"}<Icon name="arrow" size={14} /></Button><Button variant="ghost" size="sm" type="button" disabled={!available && !done} aria-pressed={done} onClick={() => toggleDone(step.featureKey)}>{done ? "取消完成" : "标记完成"}</Button></div>
            </article>;
          })}
        </section>
        <div className="fyt-workflow-note"><Icon name="check" size={16} /><span>步骤顺序仅作建议；完成业务任务后返回本页会自动勾选，也可以随时手动标记或取消。资料尚未准备好时，可先打开下一步查看模板，再返回继续。</span></div>
      </main>
    </div>
  </div>;
}

export default WorkflowCenterPage;
