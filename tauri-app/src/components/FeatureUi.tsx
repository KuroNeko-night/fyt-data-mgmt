import { useEffect, useRef, useState, type ReactNode } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import Icon from "./Icon";
import { chooseFiles, fileName, openLocalPath, type FileFilter } from "../lib/files";
import { isTauriRuntime } from "../lib/bridge";

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

export function FilePickerField({
  label, description, value, onChange, multiple = false, directory = false,
  optional = false, filters, reorderable = false,
}: FilePickerFieldProps) {
  const [pickerError, setPickerError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fieldRef = useRef<HTMLElement | null>(null);
  const valueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  valueRef.current = value;
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: () => void = () => {};
    let disposed = false;
    const contains = (position: { x: number; y: number }) => {
      const rect = fieldRef.current?.getBoundingClientRect();
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
      const extensions = new Set((filters || []).flatMap((filter) => filter.extensions).map((item) => item.toLowerCase()));
      const accepted = directory
        ? event.payload.paths.slice(0, 1)
        : event.payload.paths.filter((path) => !extensions.size || extensions.has(path.split(".").pop()?.toLowerCase() || ""));
      if (!accepted.length) {
        setPickerError("拖入的文件类型不符合当前要求。");
        return;
      }
      const next = multiple
        ? Array.from(new Set([...valueRef.current, ...accepted]))
        : accepted.slice(0, 1);
      setPickerError("");
      onChangeRef.current(next);
    }).then((remove) => {
      if (disposed) remove(); else unlisten = remove;
    }).catch((reason) => setPickerError(reason instanceof Error ? reason.message : String(reason)));
    return () => { disposed = true; unlisten(); };
  }, [directory, filters, multiple]);

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
      className={`file-picker-field ${dragActive ? "drag-active" : ""} ${value.length ? "has-files" : ""}`}
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
      <div className="field-heading">
        <div><strong>{label}</strong>{optional ? <span>可选</span> : null}<p>{description}</p></div>
        <button type="button" className="secondary-button" onClick={() => void select()}>
          <Icon name={directory ? "folder" : "plus"} size={16} />选择{directory ? "文件夹" : "文件"}
        </button>
      </div>
      {value.length ? (
        <div className="selected-files">
          {value.map((path, index) => (
            <div key={path}><span title={path}>{fileName(path)}</span>{reorderable ? <><button type="button" disabled={index === 0} aria-label={`上移 ${fileName(path)}`} onClick={() => { const next = [...value]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next); }}>↑</button><button type="button" disabled={index === value.length - 1} aria-label={`下移 ${fileName(path)}`} onClick={() => { const next = [...value]; [next[index], next[index + 1]] = [next[index + 1], next[index]]; onChange(next); }}>↓</button></> : null}<button type="button" aria-label={`移除 ${fileName(path)}`} onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}>×</button></div>
          ))}
        </div>
      ) : <div className="file-empty"><span className="drop-orbit"><Icon name={directory ? "folder" : "plus"} size={18} /></span><span>尚未选择{directory ? "文件夹" : "文件"}，也可直接拖放到此区域</span></div>}
      {pickerError ? <div className="notice error">{pickerError}</div> : null}
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

export function TaskPanel({
  busy, error, logs, canRun, runLabel, onRun, children, outDir, outputPath, progress, onCancel,
}: TaskPanelProps) {
  const [actionError, setActionError] = useState("");
  const succeeded = !busy && !error && Boolean(outputPath || outDir);

  useEffect(() => setActionError(""), [outDir, outputPath]);

  async function openResult(path: string) {
    setActionError("");
    try {
      await openLocalPath(path);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section className={`task-panel ${busy ? "is-busy" : ""} ${error ? "is-error" : ""} ${succeeded ? "is-success" : ""}`} data-tour="task-panel" data-tour-title={runLabel} aria-live="polite">
      <div className="task-actions">
        <div><span className={`status-dot ${error ? "error" : busy ? "warn" : canRun ? "ok" : ""}`} /><strong>{error ? "处理失败" : busy ? "正在处理" : canRun ? "准备就绪" : "等待输入"}</strong></div>
        <div>
          {outputPath ? <button type="button" className="secondary-button" onClick={() => void openResult(outputPath)}>打开结果</button> : null}
          {outDir ? <button type="button" className="secondary-button" onClick={() => void openResult(outDir)}>打开输出目录</button> : null}
          {busy && onCancel ? <button type="button" className="secondary-button danger-button" onClick={onCancel}>取消任务</button> : null}
          <button type="button" className="primary-button" disabled={!canRun || busy} onClick={onRun}>{busy ? "处理中…" : runLabel}</button>
        </div>
      </div>
      {busy ? <div className="task-progress" aria-label={`处理进度 ${progress ?? 0}%`}><i style={{ width: `${Math.max(2, progress ?? 4)}%` }}><b /></i></div> : null}
      {error ? <div className="notice error">{error}</div> : null}
      {actionError ? <div className="notice error">{actionError}</div> : null}
      {children}
      {logs.length ? <details className="task-log"><summary>处理日志 · {logs.length} 条</summary><pre>{logs.join("\n")}</pre></details> : null}
    </section>
  );
}

export function FieldRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="field-row" data-tour="parameter" data-tour-title={label} data-tour-description={hint}><span><strong>{label}</strong>{hint ? <small>{hint}</small> : null}</span><div>{children}</div></label>;
}

export function ResultSummary({ children }: { children: ReactNode }) {
  return <div className="result-summary" data-tour="result-summary"><span className="result-arc" aria-hidden="true"><Icon name="check" size={15} /></span><div>{children}</div></div>;
}
