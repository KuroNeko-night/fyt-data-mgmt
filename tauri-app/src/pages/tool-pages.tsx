import { useEffect, useState } from "react";
import { bridgeRequest } from "../lib/bridge";
import { fileName } from "../lib/files";
import { FilePickerField, FieldRow, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeAction, useBridgeTask } from "../hooks/useBridgeTask";

const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls", "csv"] }];
const pdfFilters = [{ name: "PDF 文件", extensions: ["pdf"] }];

interface RenameRule {
  find: string; replace: string; use_regex: boolean; prefix: string; suffix: string;
  base_name: string; seq_enabled: boolean; seq_start: number; seq_digits: number;
  seq_sep: string; ext_lower: boolean;
}
interface RenamePlan { items: Array<{ old_path: string; old_name: string; new_name: string; status: string; note: string }>; summary: { ok: number; blocked: number; same: number; total: number }; }
interface RenameResult { count: number; failed: Array<[string, string]>; undo_map: Array<[string, string]>; paths: string[]; }

export function RenamePage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [rule, setRule] = useState<RenameRule>({ find: "", replace: "", use_regex: false, prefix: "", suffix: "", base_name: "", seq_enabled: false, seq_start: 1, seq_digits: 3, seq_sep: "_", ext_lower: false });
  const preview = useBridgeAction<RenamePlan>();
  const task = useBridgeTask<RenameResult>();
  const undo = useBridgeAction<{ count: number; failed: Array<[string, string]> }>();
  const setText = (key: keyof RenameRule, value: string | number | boolean) => {
    setRule((current) => ({ ...current, [key]: value }));
    preview.reset();
    task.reset();
    undo.reset();
  };
  async function apply() {
    const result = await task.run("rename.apply", { paths, rule });
    if (result) { setPaths(result.paths); await preview.run("rename.preview", { paths: result.paths, rule }); }
  }
  async function undoLast() {
    if (!task.result?.undo_map.length) return;
    const result = await undo.run("rename.undo", { undo_map: task.result.undo_map });
    if (result) {
      const restored = task.result.undo_map.map(([, origin]) => origin);
      setPaths(restored);
      await preview.run("rename.preview", { paths: restored, rule });
    }
  }
  return <div className="page-flow wide-flow"><section className="feature-form">
    <FilePickerField label="待重命名文件" description="按选择顺序生成序号；可用箭头调整顺序，原地重命名，先预览再应用。" value={paths} onChange={(next) => { setPaths(next); preview.reset(); task.reset(); undo.reset(); }} multiple reorderable />
    <section className="option-card"><h3>重命名规则</h3><div className="form-grid"><FieldRow label="查找"><input value={rule.find} onChange={(event) => setText("find", event.target.value)} /></FieldRow><FieldRow label="替换为"><input value={rule.replace} onChange={(event) => setText("replace", event.target.value)} /></FieldRow><FieldRow label="前缀"><input value={rule.prefix} onChange={(event) => setText("prefix", event.target.value)} /></FieldRow><FieldRow label="后缀"><input value={rule.suffix} onChange={(event) => setText("suffix", event.target.value)} /></FieldRow><FieldRow label="统一基名"><input value={rule.base_name} onChange={(event) => setText("base_name", event.target.value)} /></FieldRow><FieldRow label="序号起始 / 位数"><div className="inline-fields"><input type="number" min="0" value={rule.seq_start} onChange={(event) => setText("seq_start", Number(event.target.value))} /><input type="number" min="1" max="8" value={rule.seq_digits} onChange={(event) => setText("seq_digits", Number(event.target.value))} /><input value={rule.seq_sep} onChange={(event) => setText("seq_sep", event.target.value)} /></div></FieldRow></div><div className="check-grid"><label className="check-row"><input type="checkbox" checked={rule.use_regex} onChange={(event) => setText("use_regex", event.target.checked)} />按正则表达式</label><label className="check-row"><input type="checkbox" checked={rule.seq_enabled} onChange={(event) => setText("seq_enabled", event.target.checked)} />追加序号</label><label className="check-row"><input type="checkbox" checked={rule.ext_lower} onChange={(event) => setText("ext_lower", event.target.checked)} />扩展名转小写</label></div><button className="secondary-button" disabled={!paths.length || preview.busy} onClick={() => void preview.run("rename.preview", { paths, rule })}>{preview.busy ? "预览中…" : "刷新预览"}</button>{preview.error ? <div className="notice error">{preview.error}</div> : null}</section>
    {preview.result ? <section className="table-card"><div className="table-toolbar"><strong>可重命名 {preview.result.summary.ok} 个</strong><span>冲突 {preview.result.summary.blocked} · 无变化 {preview.result.summary.same}</span></div><div className="table-scroll"><table><thead><tr><th>原文件名</th><th>新文件名</th><th>状态</th></tr></thead><tbody>{preview.result.items.map((item) => <tr key={item.old_path}><td>{item.old_name}</td><td>{item.new_name || "—"}</td><td><span className={`task-status ${item.status === "ok" ? "ok" : "failed"}`}>{item.status}{item.note ? ` · ${item.note}` : ""}</span></td></tr>)}</tbody></table></div></section> : null}
    <TaskPanel busy={task.busy} error={task.error || undo.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(preview.result?.summary.ok)} runLabel="应用重命名" onRun={() => void apply()}>
      {task.result ? <ResultSummary><strong>已重命名 {task.result.count} 个文件</strong><span>失败 {task.result.failed.length} 个</span><button className="secondary-button" disabled={undo.busy || !task.result.undo_map.length} onClick={() => void undoLast()}>{undo.busy ? "撤销中…" : "撤销上次"}</button></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

const textOperations = [
  ["dedup", "行去重"], ["sort", "排序"], ["reverse", "倒序"],
  ["remove_empty", "去空行"], ["trim", "去首尾空格"], ["collapse", "压缩空格"],
  ["upper", "转大写"], ["lower", "转小写"], ["line_numbers", "加行号"],
  ["email", "提取邮箱"], ["phone", "提取手机号"], ["url", "提取网址"],
];

export function TextPage() {
  const [source, setSource] = useState("");
  const [result, setResult] = useState("");
  const [options, setOptions] = useState({ ignore_case: false, numeric: false, reverse: false, pad: false });
  const action = useBridgeAction<{ text: string; stats: { lines: number; chars: number } }>();
  async function transform(operation: string) {
    setResult("");
    const response = await action.run("text.transform", { text: source, operation, options });
    if (response) setResult(response.text);
  }
  return <div className="page-flow wide-flow"><section className="text-workbench"><div className="editor-panel"><div><strong>原文本</strong><span>{source.length} 字符</span></div><textarea value={source} onChange={(event) => setSource(event.target.value)} placeholder="在这里粘贴或输入文本" /><button className="text-button" onClick={() => setSource("")}>清空</button></div><div className="editor-panel"><div><strong>结果</strong><span>{result.length} 字符</span></div><textarea value={result} readOnly placeholder="处理结果显示在这里" /><div><button className="text-button" disabled={!result} onClick={() => setSource(result)}>回填到原文本</button><button className="text-button" disabled={!result} onClick={() => void navigator.clipboard.writeText(result)}>复制结果</button></div></div></section>
    <section className="option-card"><div className="check-grid"><label className="check-row"><input type="checkbox" checked={options.ignore_case} onChange={(event) => setOptions({ ...options, ignore_case: event.target.checked })} />忽略大小写</label><label className="check-row"><input type="checkbox" checked={options.numeric} onChange={(event) => setOptions({ ...options, numeric: event.target.checked })} />按数字排序</label><label className="check-row"><input type="checkbox" checked={options.reverse} onChange={(event) => setOptions({ ...options, reverse: event.target.checked })} />降序</label><label className="check-row"><input type="checkbox" checked={options.pad} onChange={(event) => setOptions({ ...options, pad: event.target.checked })} />行号补零</label></div><div className="operation-grid">{textOperations.map(([key, label]) => <button key={key} className="secondary-button" disabled={action.busy} onClick={() => void transform(key)}>{label}</button>)}</div>{action.error ? <div className="notice error">{action.error}</div> : null}</section>
  </div>;
}

interface FileToolResult { out_dir: string; out_files: string[]; }

export function PdfPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [mode, setMode] = useState("merge");
  const [splitMode, setSplitMode] = useState("each");
  const [spec, setSpec] = useState("");
  const [pages, setPages] = useState<number | null>(null);
  const task = useBridgeTask<FileToolResult>();
  const changeMode = (next: string) => { setMode(next); setSpec(""); task.reset(); };
  useEffect(() => {
    let active = true;
    if (!paths[0] || mode === "merge") { setPages(null); return () => { active = false; }; }
    bridgeRequest<{ pages: number }>("pdf.info", { path: paths[0] }).then((response) => { if (active) setPages(response.pages); }).catch(() => { if (active) setPages(null); });
    return () => { active = false; };
  }, [paths, mode]);
  const needsSpec = mode === "extract" || mode === "delete" || (mode === "split" && splitMode === "ranges");
  const canRun = mode === "merge" ? paths.length >= 2 : Boolean(paths.length && (!needsSpec || spec.trim()));
  return <div className="page-flow wide-flow"><section className="feature-form"><section className="option-card"><div className="segmented four">{[["merge", "合并"], ["split", "拆分"], ["extract", "提取页"], ["delete", "删除页"]].map(([key, label]) => <button key={key} className={mode === key ? "active" : ""} onClick={() => changeMode(key)}>{label}</button>)}</div></section><FilePickerField label="PDF 文件" description="合并时按选择顺序；其他操作仅处理第一个文件。" value={paths} onChange={(next) => { setPaths(next); task.reset(); }} multiple filters={pdfFilters} />
    <section className="option-card">{mode === "split" ? <FieldRow label="拆分方式"><select value={splitMode} onChange={(event) => { setSplitMode(event.target.value); setSpec(""); task.reset(); }}><option value="each">每页一个文件</option><option value="ranges">按范围分段</option></select></FieldRow> : null}{needsSpec ? <FieldRow label="页码范围" hint="例如 1,3,5-8,12-"><input value={spec} onChange={(event) => { setSpec(event.target.value); task.reset(); }} /></FieldRow> : null}{pages !== null ? <p className="field-help">{fileName(paths[0])} 共 {pages} 页</p> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={canRun} runLabel="开始处理" onRun={() => void task.run("pdf.run", { paths, mode, split_mode: splitMode, spec })} outDir={task.outDir}>{task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个 PDF</strong><span>{task.outDir}</span></ResultSummary> : null}</TaskPanel></section></div>;
}

export function ExcelToolsPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [mode, setMode] = useState("merge");
  const [target, setTarget] = useState("xlsx");
  const [hasHeader, setHasHeader] = useState(true);
  const [keepFormula, setKeepFormula] = useState(false);
  const task = useBridgeTask<FileToolResult>();
  const changeMode = (next: string) => { setMode(next); task.reset(); };
  const canRun = mode === "merge" || mode === "stack" ? paths.length >= 2 : paths.length >= 1;
  return <div className="page-flow wide-flow"><section className="feature-form"><section className="option-card"><div className="segmented four">{[["merge", "多簿合并"], ["split", "按 Sheet 拆分"], ["convert", "格式转换"], ["stack", "纵向合并"]].map(([key, label]) => <button key={key} className={mode === key ? "active" : ""} onClick={() => changeMode(key)}>{label}</button>)}</div></section><FilePickerField label="表格文件" description="支持 xlsx、xlsm、xls、csv，可多选。" value={paths} onChange={(next) => { setPaths(next); task.reset(); }} multiple filters={excelFilters} />
    <section className="option-card">{mode === "convert" ? <FieldRow label="转换目标"><select value={target} onChange={(event) => setTarget(event.target.value)}><option value="xlsx">xlsx</option><option value="csv">CSV（每个 Sheet 一个文件）</option></select></FieldRow> : null}{mode === "merge" ? <label className="check-row"><input type="checkbox" checked={keepFormula} onChange={(event) => setKeepFormula(event.target.checked)} />保留公式</label> : null}{mode === "stack" ? <label className="check-row"><input type="checkbox" checked={hasHeader} onChange={(event) => setHasHeader(event.target.checked)} />首行是表头，仅保留一次并添加来源文件列</label> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={canRun} runLabel="开始处理" onRun={() => void task.run("excel.run", { paths, mode, target, has_header: hasHeader, keep_formula: keepFormula })} outDir={task.outDir}>{task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个文件</strong><span>{task.outDir}</span></ResultSummary> : null}</TaskPanel></section></div>;
}

interface ComparePrepare { common: string[]; headers1: string[]; headers2: string[]; }
interface CompareResult { out_dir: string; report_path: string; counts: { diffs: number; only_a: number; only_b: number; same: number }; diffs: Array<{ key: string; column: string; a: unknown; b: unknown }>; only_a: Array<{ key: string; row: Record<string, unknown> }>; only_b: Array<{ key: string; row: Record<string, unknown> }>; }

function useSheets(path: string) {
  const [sheets, setSheets] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    if (!path) { setSheets([]); return () => { active = false; }; }
    bridgeRequest<{ sheets: string[] }>("system.sheets", { path }).then((response) => { if (active) setSheets(response.sheets || []); }).catch(() => { if (active) setSheets([]); });
    return () => { active = false; };
  }, [path]);
  return sheets;
}

export function ComparePage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [keyColumn, setKeyColumn] = useState("");
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const prepare = useBridgeAction<ComparePrepare>();
  const task = useBridgeTask<CompareResult>();
  const resetComparison = () => { setKeyColumn(""); prepare.reset(); task.reset(); };
  async function loadColumns() {
    const result = await prepare.run("compare.prepare", { file1, file2, sheet1, sheet2 });
    if (result) setKeyColumn((current) => result.common.includes(current) ? current : result.common[0] || "");
  }
  return <div className="page-flow wide-flow"><section className="feature-form"><FilePickerField label="A 表" description="通常放程序输出或新版。" value={file1} onChange={(next) => { setFile1(next); setSheet1(""); resetComparison(); }} filters={excelFilters} />{sheets1.length > 1 ? <FieldRow label="A 表工作表"><select value={sheet1} onChange={(event) => { setSheet1(event.target.value); resetComparison(); }}><option value="">自动识别</option>{sheets1.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow> : null}<FilePickerField label="B 表" description="通常放手工结果或旧版。" value={file2} onChange={(next) => { setFile2(next); setSheet2(""); resetComparison(); }} filters={excelFilters} />{sheets2.length > 1 ? <FieldRow label="B 表工作表"><select value={sheet2} onChange={(event) => { setSheet2(event.target.value); resetComparison(); }}><option value="">自动识别</option>{sheets2.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow> : null}
    <section className="option-card"><div className="section-heading compact"><div><h3>关键列</h3><p>先读取两表公共列，再选择配对依据。</p></div><button className="secondary-button" disabled={!file1.length || !file2.length || prepare.busy} onClick={() => void loadColumns()}>{prepare.busy ? "读取中…" : "读取公共列"}</button></div>{prepare.error ? <div className="notice error">{prepare.error}</div> : null}{prepare.result ? <FieldRow label="按此列配对"><select value={keyColumn} onChange={(event) => setKeyColumn(event.target.value)}>{prepare.result.common.map((column) => <option key={column}>{column}</option>)}</select></FieldRow> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(keyColumn)} runLabel="开始比对" onRun={() => void task.run("compare.run", { file1, file2, sheet1, sheet2, key: keyColumn })} outDir={task.outDir} outputPath={task.result?.report_path}>{task.result ? <><ResultSummary><strong>差异 {task.result.counts.diffs} 处</strong><span>只在 A {task.result.counts.only_a} · 只在 B {task.result.counts.only_b}</span></ResultSummary><div className="editable-table"><table><thead><tr><th>关键值</th><th>列</th><th>A</th><th>B</th></tr></thead><tbody>{task.result.diffs.slice(0, 100).map((item, index) => <tr key={`${item.key}-${item.column}-${index}`}><td>{item.key}</td><td>{item.column}</td><td>{String(item.a ?? "")}</td><td>{String(item.b ?? "")}</td></tr>)}</tbody></table></div></> : null}</TaskPanel></section></div>;
}
