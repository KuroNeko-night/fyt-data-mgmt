/**
 * 桌面端业务页面共用的文件输入、任务状态和结果摘要组件。
 *
 * 本模块只管理界面交互：文件选择由 `lib/files` 统一调用 Tauri 能力，
 * 业务执行仍由页面和桥接层负责，组件不会自行读取文件或推断业务内容。
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import Icon from "./Icon";
import { chooseFiles, fileName, openLocalPath, type FileFilter } from "../lib/files";
import { isTauriRuntime } from "../lib/bridge";
import Button from "../ui/Button";
import IconButton from "../ui/IconButton";
import Notice from "../ui/Notice";

interface FilePickerFieldProps {
  label: string;
  description: string;
  value: string[];
  onChange: (paths: string[]) => void;
  multiple?: boolean;
  directory?: boolean;
  optional?: boolean;
  filters?: FileFilter[];
  reorderable?: boolean;
}

/**
 * 展示受控文件选择区，并同时兼容系统选择器与拖放输入。
 *
 * `value` 始终由父组件持有；多选时会在保留原顺序的前提下去重，目录模式
 * 只接受首个路径。Tauri 的拖放事件挂在 WebView 上而不是当前 DOM 节点上，
 * 因此需要额外判断指针坐标是否落在本组件的可视区域内。
 */
export function FilePickerField({
  label, description, value, onChange, multiple = false, directory = false,
  optional = false, filters, reorderable = false,
}: FilePickerFieldProps) {
  const [pickerError, setPickerError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fieldRef = useRef<HTMLElement | null>(null);
  // WebView 监听器只在选择规则变化时重建；引用保存最新受控值，避免回调闭包使用旧文件列表。
  const valueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  valueRef.current = value;
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: () => void = () => {};
    let disposed = false;

    /** 将 Tauri 返回的物理像素坐标换算为浏览器布局像素，并判断是否命中当前选择区。 */
    const contains = (position: { x: number; y: number }) => {
      const rect = fieldRef.current?.getBoundingClientRect();
      // 高分屏下 Tauri 拖放坐标按物理像素计数，而 DOMRect 使用 CSS 像素，必须除以缩放倍率。
      const scale = window.devicePixelRatio || 1;
      const x = position.x / scale;
      const y = position.y / scale;
      return Boolean(rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom);
    };
    void getCurrentWebview().onDragDropEvent((event) => {
      if (event.payload.type === "leave") {
        setDragActive(false);
        return;
      }
      const inside = contains(event.payload.position);
      setDragActive(inside);
      if (event.payload.type !== "drop" || !inside) return;
      // 空扩展名集合表示不限制类型；比较时统一转成小写，兼容 Windows 大小写不敏感路径。
      const extensions = new Set((filters || []).flatMap((filter) => filter.extensions).map((item) => item.toLowerCase()));
      const accepted = directory
        ? event.payload.paths.slice(0, 1)
        : event.payload.paths.filter((path) => !extensions.size || extensions.has(path.split(".").pop()?.toLowerCase() || ""));
      if (!accepted.length) {
        setPickerError("拖入的文件类型不符合当前要求。");
        return;
      }
      const next = multiple
        // Set 同时完成去重并保留已有文件在前、新拖入文件在后的稳定顺序。
        ? Array.from(new Set([...valueRef.current, ...accepted]))
        : accepted.slice(0, 1);
      setPickerError("");
      onChangeRef.current(next);
    }).then((remove) => {
      // 监听注册是异步的；组件若已卸载，应立即执行刚取得的清理函数，不能遗留全局监听器。
      if (disposed) remove(); else unlisten = remove;
    }).catch((reason) => setPickerError(reason instanceof Error ? reason.message : String(reason)));
    return () => { disposed = true; unlisten(); };
  }, [directory, filters, multiple]);

  /** 打开系统文件选择器，并把非空选择合并回父组件的受控状态。 */
  async function select() {
    setPickerError("");
    try {
      const selected = await chooseFiles({ title: `选择${label}`, multiple, directory, filters });
      if (!selected.length) return;
      const next = multiple ? Array.from(new Set([...value, ...selected])) : selected.slice(0, 1);
      onChange(next);
    } catch (reason) {
      setPickerError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section
      ref={fieldRef}
      className={`fyt-file-picker ${dragActive ? "is-drag-active" : ""} ${value.length ? "has-files" : ""}`}
      data-tour="file-input"
      data-tour-title={label}
      data-tour-description={description}
      onDragEnter={() => { if (!isTauriRuntime()) setDragActive(true); }}
      onDragOver={(event) => { if (!isTauriRuntime()) event.preventDefault(); }}
      onDragLeave={(event) => {
        if (!isTauriRuntime() && !event.currentTarget.contains(event.relatedTarget as Node | null)) setDragActive(false);
      }}
      onDrop={(event) => { if (!isTauriRuntime()) { event.preventDefault(); setDragActive(false); } }}
    >
      <div className="fyt-field-heading">
        <div><strong>{label}</strong>{optional ? <span>可选</span> : null}<p>{description}</p></div>
        <Button type="button" variant="secondary" size="sm" onClick={() => void select()}>
          <Icon name={directory ? "folder" : "plus"} size={16} />选择{directory ? "文件夹" : "文件"}
        </Button>
      </div>
      {value.length ? (
        <div className="fyt-selected-files">
          {value.map((path, index) => (
            <div key={path}><span title={path}>{fileName(path)}</span>{reorderable ? <><IconButton size="sm" label={`上移 ${fileName(path)}`} disabled={index === 0} onClick={() => { const next = [...value]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next); }}><Icon name="up" size={14} /></IconButton><IconButton size="sm" label={`下移 ${fileName(path)}`} disabled={index === value.length - 1} onClick={() => { const next = [...value]; [next[index], next[index + 1]] = [next[index + 1], next[index]]; onChange(next); }}><Icon name="down" size={14} /></IconButton></> : null}<IconButton size="sm" label={`移除 ${fileName(path)}`} onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}><Icon name="close" size={14} /></IconButton></div>
          ))}
        </div>
      ) : <div className="fyt-file-empty"><span className="fyt-drop-orbit"><Icon name={directory ? "folder" : "plus"} size={18} /></span><span>尚未选择{directory ? "文件夹" : "文件"}，也可直接拖放到此区域</span></div>}
      {pickerError ? <Notice tone="error">{pickerError}</Notice> : null}
    </section>
  );
}

interface TaskPanelProps {
  busy: boolean;
  error: string;
  logs: string[];
  canRun: boolean;
  runLabel: string;
  onRun: () => void;
  children?: ReactNode;
  outDir?: string;
  outputPath?: string;
  progress?: number | null;
  onCancel?: () => void;
}

const WORKFLOW_STEPS = ["准备文件", "检查设置", "运行并查看结果"];

/** 根据当前阶段渲染固定的三步业务流程，`done` 表示已完成边界，`step` 表示当前高亮边界。 */
function WorkflowSteps({ step, done }: { step: number; done: number }) {
  return <div className="fyt-workflow-steps" aria-label="处理流程">
    {WORKFLOW_STEPS.map((label, index) => {
      const number = index + 1;
      return <div key={label} className={`fyt-workflow-step ${number <= step ? "is-active" : ""} ${number <= done ? "is-done" : ""}`}>
        <span className="fyt-workflow-dot">{number <= done ? <Icon name="check" size={12} /> : number}</span>
        <strong>{label}</strong>
        {number < WORKFLOW_STEPS.length ? <i className="fyt-workflow-line" /> : null}
      </div>;
    })}
  </div>;
}

/**
 * 汇总业务任务的可运行状态、执行进度、错误信息和结果入口。
 *
 * 组件不持有任务本身，只根据父页面传入的状态派生展示阶段。打开本地路径失败
 * 属于界面动作失败，不应覆盖业务任务原有的成功或失败结果，因此使用独立错误状态。
 */
export function TaskPanel({
  busy, error, logs, canRun, runLabel, onRun, children, outDir, outputPath, progress, onCancel,
}: TaskPanelProps) {
  const [actionError, setActionError] = useState("");
  // 只有任务已停止、无业务错误且存在可访问结果时，才把流程判定为完整成功。
  const succeeded = !busy && !error && Boolean(outputPath || outDir);
  const step = succeeded || busy ? 3 : canRun ? 2 : 1;
  const done = succeeded ? 3 : busy ? 2 : canRun ? 1 : 0;

  // 新结果替换旧结果时清除此前的“打开路径”错误，避免误导用户认为新产物也不可访问。
  useEffect(() => setActionError(""), [outDir, outputPath]);

  /** 调用桌面系统打开结果文件或目录，并把系统调用错误限制在当前任务面板内。 */
  async function openResult(path: string) {
    setActionError("");
    try {
      await openLocalPath(path);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section className={`fyt-task-panel ${busy ? "is-busy" : ""} ${error ? "is-error" : ""} ${succeeded ? "is-success" : ""}`} data-tour="task-panel" data-tour-title={runLabel} aria-live="polite">
      <WorkflowSteps step={step} done={done} />
      <div className="fyt-task-actions">
        <div><span className={`fyt-status-dot ${error ? "is-error" : busy ? "is-warning" : canRun ? "is-success" : ""}`} /><strong>{error ? "处理失败" : busy ? "正在处理" : canRun ? "准备就绪" : "等待输入"}</strong></div>
        <div>
          {outputPath ? <Button type="button" variant="secondary" size="sm" onClick={() => void openResult(outputPath)}>打开结果</Button> : null}
          {outDir ? <Button type="button" variant="secondary" size="sm" onClick={() => void openResult(outDir)}>打开输出目录</Button> : null}
          {busy && onCancel ? <Button type="button" variant="danger" size="sm" onClick={onCancel}>取消任务</Button> : null}
          <Button type="button" variant="primary" size="sm" disabled={!canRun || busy} onClick={onRun}>{busy ? "处理中…" : runLabel}</Button>
        </div>
      </div>
      {busy ? <div className="fyt-task-progress" aria-label={`处理进度 ${progress ?? 0}%`}><i style={{ width: `${Math.max(2, progress ?? 4)}%` }} /></div> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {actionError ? <Notice tone="error">{actionError}</Notice> : null}
      {children}
      {logs.length && error ? <details className="fyt-task-log"><summary>查看处理提示 · {logs.length} 条</summary><pre>{logs.join("\n")}</pre></details> : null}
    </section>
  );
}

/** 统一业务参数标签、辅助说明和引导标记，具体输入控件由调用方提供。 */
export function FieldRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="fyt-field-row" data-tour="parameter" data-tour-title={label} data-tour-description={hint}><span><strong>{label}</strong>{hint ? <small>{hint}</small> : null}</span><div>{children}</div></label>;
}

/** 为结构化结果提供统一的成功视觉和新手引导锚点，不改变子内容的语义。 */
export function ResultSummary({ children }: { children: ReactNode }) {
  return <div className="fyt-result-summary" data-tour="result-summary"><span className="fyt-result-mark" aria-hidden="true"><Icon name="check" size={15} /></span><div>{children}</div></div>;
}
