/**
 * 桌面端表格业务页面集合。
 *
 * 各页面只收集文件、可调参数和人工复核选择，再通过桥接动作调用 `core/`；
 * 表头识别、主数据补全、可信度、文件生成与业务计算不在 React 中重复实现。
 * 需要复核的业务严格保留“分析—确认—执行”两阶段状态。
 */
import { useEffect, useMemo, useState } from "react";
import { bridgeRequest } from "../lib/bridge";
import { fileName } from "../lib/files";
import { FilePickerField, FieldRow, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeAction, useBridgeTask } from "../hooks/useBridgeTask";
import BusinessResultView from "../ui/BusinessResultView";

const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls", "csv"] }];

/** 读取单个表格的工作表名称，并在路径快速切换时丢弃过期响应。 */
function useSheets(path: string) {
  const [sheets, setSheets] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    if (!path) {
      setSheets([]);
      return () => { active = false; };
    }
    bridgeRequest<{ sheets: string[] }>("system.sheets", { path })
      .then((response) => { if (active) setSheets(response.sheets || []); })
      .catch(() => { if (active) setSheets([]); });
    return () => { active = false; };
  }, [path]);
  return sheets;
}

/** 仅在文件含多个工作表时显示人工选择，单工作表文件继续由核心层自动识别。 */
function SheetSelect({ label, sheets, value, onChange }: { label: string; sheets: string[]; value: string; onChange: (value: string) => void }) {
  if (sheets.length <= 1) return null;
  return <FieldRow label={label} hint="留空时由系统自动识别"><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">自动识别</option>{sheets.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></FieldRow>;
}

/** 将分析计划中的任意嵌套值压缩为复核列表可读文本，不修改原始计划结构。 */
function reviewValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(reviewValue).join("、");
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${key}：${reviewValue(item)}`).join("；");
  return String(value);
}

interface AttendanceResult { out_files: string[]; out_dir: string; }

/** 收集打卡来源、待填模板和工时口径，批量生成不覆盖原文件的考勤结果。 */
export function AttendancePage() {
  const [sources, setSources] = useState<string[]>([]);
  const [targets, setTargets] = useState<string[]>([]);
  const [options, setOptions] = useState({
    workday_hours: 9,
    overtime: true,
    auto_actual: true,
    conflict: "last",
    day_max_hours: 16,
    night_shift: true,
    night_start_hour: 17,
    night_workday_hours: 11,
    night_max_hours: 16,
    skip_extra: "",
  });
  const task = useBridgeTask<AttendanceResult>();
  // 数字参数变化后旧输出不再对应当前口径，因此同步重置任务展示。
  const setNumber = (key: keyof typeof options, value: string) => {
    setOptions((current) => ({ ...current, [key]: Number(value) }));
    task.reset();
  };
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="系统数据（打卡来源）" description="考勤机或系统导出的原始打卡表，可多选。" value={sources} onChange={(next) => { setSources(next); task.reset(); }} multiple filters={excelFilters} />
    <FilePickerField label="待填考勤表（目标）" description="需要填写的考勤模板，可多选，原文件不会被覆盖。" value={targets} onChange={(next) => { setTargets(next); task.reset(); }} multiple filters={excelFilters} />
    <section className="fyt-option-card"><h3>计算口径</h3><div className="fyt-form-grid">
      <FieldRow label="白班标准工时（小时）"><input type="number" min="1" max="24" step="0.5" value={options.workday_hours} onChange={(event) => setNumber("workday_hours", event.target.value)} /></FieldRow>
      <FieldRow label="重复打卡记录"><select value={options.conflict} onChange={(event) => { setOptions({ ...options, conflict: event.target.value }); task.reset(); }}><option value="last">后者覆盖</option><option value="first">先者优先</option><option value="warn">不覆盖，仅提示</option></select></FieldRow>
      <FieldRow label="白班合理上限"><input type="number" min="1" max="24" step="0.5" value={options.day_max_hours} onChange={(event) => setNumber("day_max_hours", event.target.value)} /></FieldRow>
      <FieldRow label="夜班开始时间（时）"><input type="number" min="0" max="23.5" step="0.5" value={options.night_start_hour} onChange={(event) => setNumber("night_start_hour", event.target.value)} /></FieldRow>
      <FieldRow label="夜班标准工时"><input type="number" min="1" max="24" step="0.5" value={options.night_workday_hours} onChange={(event) => setNumber("night_workday_hours", event.target.value)} /></FieldRow>
      <FieldRow label="夜班合理上限"><input type="number" min="1" max="24" step="0.5" value={options.night_max_hours} onChange={(event) => setNumber("night_max_hours", event.target.value)} /></FieldRow>
    </div><FieldRow label="额外假休标记" hint="用逗号或换行分隔"><textarea value={options.skip_extra} placeholder="例如：培训、外勤" onChange={(event) => { setOptions({ ...options, skip_extra: event.target.value }); task.reset(); }} /></FieldRow><label className="fyt-check-row"><input type="checkbox" checked={options.auto_actual} onChange={(event) => { setOptions({ ...options, auto_actual: event.target.checked }); task.reset(); }} />自动按半小时计算实际上/下班时间</label><label className="fyt-check-row"><input type="checkbox" checked={options.night_shift} onChange={(event) => { setOptions({ ...options, night_shift: event.target.checked }); task.reset(); }} />启用跨零点夜班识别</label><label className="fyt-check-row"><input type="checkbox" checked={options.overtime} onChange={(event) => { setOptions({ ...options, overtime: event.target.checked }); task.reset(); }} />计算加班列</label></section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={sources.length > 0 && targets.length > 0} runLabel="开始填报" onRun={() => void task.run("attendance.run", { sources, targets, options: { ...options, skip_extra: options.skip_extra.split(/[，,、\n\r]+/).map((item) => item.trim()).filter(Boolean) } })} outDir={task.outDir}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>已生成 {task.result.out_files.length} 个已填写考勤表</strong></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface ReconcilePlan {
  target: { sheet: string; sheets: string[]; name_col: number; comp_col: number; work_col: number; names: string[] };
  only_labor: string[];
  only_zong: string[];
}
interface ReconcileResult { filled_path: string; summary_path: string; credibility: { level: string; score: number }; anomalies: unknown[]; }

/**
 * 执行工时对账的两阶段流程：先识别目标列和姓名差异，再携带人工配对选择生成结果。
 * 用户也可跳过分析，此时 `choices` 为 `null`，核心层按默认识别规则执行。
 */
export function ReconcilePage() {
  const [target, setTarget] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [labor, setLabor] = useState<string[]>([]);
  const [sheet, setSheet] = useState("");
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState({ name: "", comp: "", work: "" });
  const [tolerance, setTolerance] = useState(0.1);
  const sheets = useSheets(target[0] || "");
  const analysis = useBridgeAction<ReconcilePlan>();
  const task = useBridgeTask<ReconcileResult>();
  // 只有用户明确选择工作表时才发送覆盖项，空值保留核心层自动识别能力。
  const options = {
    tolerance,
    ...(target[0] && sheet ? { columns: { [fileName(target[0])]: { sheet } } } : {}),
  };
  // 人工选择只在存在对应分析计划时有效，避免把陈旧列号传给另一组文件。
  const choices = analysis.result ? {
    target_sheet: sheet || null,
    target_roles: Object.fromEntries(Object.entries(roles).filter(([, value]) => value).map(([key, value]) => [key, Number(value)])),
    aliases,
  } : null;
  const ready = Boolean(target.length && sources.length && labor.length);
  /** 输入文件或识别参数变化时，使全部人工复核选择及执行结果失效。 */
  function resetReview() {
    setAliases({});
    setRoles({ name: "", comp: "", work: "" });
    analysis.reset();
    task.reset();
  }
  /** 取得只读分析计划，并仅在用户尚未选择时采用系统建议的工作表。 */
  async function analyze() {
    const plan = await analysis.run("reconcile.analyze", { target, sources, labor, options });
    if (plan) setSheet((current) => current || plan.target.sheet || "");
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="待对表（目标）" description="需要被核对填写的总表，选择一个。" value={target} onChange={(next) => { setTarget(next); setSheet(""); resetReview(); }} filters={excelFilters} />
    <SheetSelect label="待对表工作表" sheets={sheets} value={sheet} onChange={(next) => { setSheet(next); resetReview(); }} />
    <FilePickerField label="数据来源" description="已填好的考勤或工时数据，可多选。" value={sources} onChange={(next) => { setSources(next); resetReview(); }} multiple filters={excelFilters} />
    <FilePickerField label="对账单 / 工时单" description="需要与来源核对的劳务对账单，可多选。" value={labor} onChange={(next) => { setLabor(next); resetReview(); }} multiple filters={excelFilters} />
    <section className="fyt-option-card"><FieldRow label="工时差异容差（小时）" hint="小于等于该值视为一致"><input type="number" min="0" max="24" step="0.05" value={tolerance} onChange={(event) => { setTolerance(Math.max(0, Number(event.target.value) || 0)); resetReview(); }} /></FieldRow></section>
    <section className="fyt-option-card"><div className="fyt-section-heading fyt-compact"><div><h3>核对确认</h3><p>先分析结构和姓名差异，再按需纠正。</p></div><button className="fyt-secondary-button" disabled={!ready || analysis.busy} onClick={() => void analyze()}>{analysis.busy ? "分析中…" : "分析并复核"}</button></div>
      {analysis.error ? <div className="fyt-page-notice error">{analysis.error}</div> : null}
      {analysis.result ? <><div className="fyt-form-grid"><FieldRow label="姓名列（1 起）" hint="已自动识别，可修改"><input value={roles.name} placeholder={String(analysis.result.target.name_col || "")} onChange={(event) => setRoles({ ...roles, name: event.target.value })} /></FieldRow><FieldRow label="公司列（1 起）" hint="已自动识别，可修改"><input value={roles.comp} placeholder={String(analysis.result.target.comp_col || "")} onChange={(event) => setRoles({ ...roles, comp: event.target.value })} /></FieldRow><FieldRow label="工时列（1 起）" hint="已自动识别，可修改"><input value={roles.work} placeholder={String(analysis.result.target.work_col || "")} onChange={(event) => setRoles({ ...roles, work: event.target.value })} /></FieldRow></div>
        {analysis.result.only_labor.length ? <div className="fyt-review-list"><strong>待配对姓名 · {analysis.result.only_labor.length}</strong>{analysis.result.only_labor.map((name) => <label key={name}><span>{name}</span><select value={aliases[name] || ""} onChange={(event) => setAliases({ ...aliases, [name]: event.target.value })}><option value="">不配对</option>{analysis.result?.only_zong.map((candidate) => <option key={candidate}>{candidate}</option>)}</select></label>)}</div> : <div className="fyt-page-notice success">姓名已全部匹配。</div>}</> : <p className="fyt-empty-message">可先复核姓名和列信息，也可以直接按默认规则处理。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={ready} runLabel="开始对账" onRun={() => void task.run("reconcile.run", { target, sources, labor, options, choices })} outDir={task.outDir} outputPath={task.result?.summary_path}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>可信度 {task.result.credibility.level} · {task.result.credibility.score}/100</strong><span>异常 {task.result.anomalies.length} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface ArrivalRow { path: string; batch_no: string; total: number; auto_total: number; missing_count: number; remark: string; include: boolean; }
interface ArrivalResult { out_file: string; out_dir: string; results: Array<[string, number, number, number]>; }

/** 预扫描送货计划中的批次与主料总类数，允许逐批修正后生成每日到料明细。 */
export function ArrivalPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [rows, setRows] = useState<ArrivalRow[]>([]);
  const [topLabel, setTopLabel] = useState("截止16点的数据");
  const prepare = useBridgeAction<{ rows: ArrivalRow[]; top_label: string }>();
  const task = useBridgeTask<ArrivalResult>();
  /** 文件选择变化后重新准备复核行，空选择直接清除计划而不发起桥接请求。 */
  async function changePaths(next: string[]) {
    setPaths(next);
    task.reset();
    if (!next.length) { setRows([]); return; }
    const result = await prepare.run("arrival.prepare", { paths: next });
    if (result) { setRows(result.rows); setTopLabel(result.top_label); }
  }
  /** 以索引更新当前分析快照中的单行，保持其余批次对象引用不变。 */
  function updateRow(index: number, patch: Partial<ArrivalRow>) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="送货计划表" description="系统扫描完整计划，筛选隐藏行也会参与总类数和未到料识别，可多选。" value={paths} onChange={(next) => void changePaths(next)} multiple filters={excelFilters} />
    <section className="fyt-option-card"><FieldRow label="报表抬头（可选）"><input value={topLabel} onChange={(event) => setTopLabel(event.target.value)} /></FieldRow>{prepare.error ? <div className="fyt-page-notice error">{prepare.error}</div> : null}
      {rows.length ? <div className="fyt-editable-table"><table><thead><tr><th>纳入</th><th>文件</th><th>批次号</th><th>主料总类数</th><th>未到料</th><th>备注</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.path}><td><input type="checkbox" checked={row.include} onChange={(event) => updateRow(index, { include: event.target.checked })} /></td><td title={row.path}>{fileName(row.path)}</td><td><input value={row.batch_no} onChange={(event) => updateRow(index, { batch_no: event.target.value })} /></td><td><input type="number" min="0" value={row.total} title={`自动识别 ${row.auto_total} 类，可人工修改`} onChange={(event) => updateRow(index, { total: Number(event.target.value) })} /></td><td>{row.missing_count} 类</td><td><input value={row.remark} onChange={(event) => updateRow(index, { remark: event.target.value })} /></td></tr>)}</tbody></table></div> : <p className="fyt-empty-message">选择文件后自动识别批次、主料总类数和非零未到料。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={rows.some((row) => row.include)} runLabel="生成到料明细" onRun={() => void task.run("arrival.run", { rows, top_label: topLabel })} outDir={task.outDir} outputPath={task.result?.out_file}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>已写入 {task.result.results.length} 个批次</strong><span>{task.result.out_file.split(/[\\/]/).pop()}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface PivotSheet { id: string; file: string; sheet: string; use: boolean; kind: string; confidence: number; reason: string; }
interface PivotHeld { sid: string; ridx: number; sheet?: string; summary?: string; rec?: unknown; }
interface PivotConflict { gk: unknown; default: string; dist?: Record<string, number>; variants?: Record<string, number>; name?: string; code?: string; spec?: string; }
interface PivotPlan { sheets: PivotSheet[]; held_index: PivotHeld[]; unit_conflicts: PivotConflict[]; spec_merges: PivotConflict[]; }
interface PivotResult { out: string; out_dir: string; report: string; groups: number; total: number; level: string; score: number; }

/**
 * 分析多份采购数据表，让用户确认纳入工作表、疑似误删行、单位冲突和规格归并，
 * 再把与系统默认值不同的最小覆盖集发送给透视表核心逻辑。
 */
export function PivotPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [plan, setPlan] = useState<PivotPlan | null>(null);
  const [sheetUse, setSheetUse] = useState<Record<string, boolean>>({});
  const [held, setHeld] = useState<Record<string, boolean>>({});
  const [unitValues, setUnitValues] = useState<Record<string, string>>({});
  const [specValues, setSpecValues] = useState<Record<string, string>>({});
  const analysis = useBridgeTask<PivotPlan>();
  const task = useBridgeTask<PivotResult>();
  /** 保存本次分析快照，并用计划默认值初始化各项受控复核选择。 */
  async function analyze() {
    const result = await analysis.run("pivot.analyze", { paths });
    if (!result) return;
    setPlan(result);
    setSheetUse(Object.fromEntries(result.sheets.map((sheet) => [sheet.id, sheet.use])));
    setHeld({});
    setUnitValues(Object.fromEntries(result.unit_conflicts.map((item, index) => [`u-${index}`, item.default || ""])));
    setSpecValues(Object.fromEntries(result.spec_merges.map((item, index) => [`s-${index}`, item.default || ""])));
  }
  // 仅发送改变过的单位和规格值，未修改项继续使用同一分析计划中的默认决策。
  const choices = plan ? {
    sheets: sheetUse,
    held: plan.held_index.map((item) => ({ sid: item.sid, ridx: item.ridx, keep: Boolean(held[`${item.sid}:${item.ridx}`]) })),
    unit_overrides: plan.unit_conflicts.map((item, index) => ({ gk: item.gk, value: unitValues[`u-${index}`] })).filter((item, index) => item.value !== (plan.unit_conflicts[index].default || "")),
    spec_overrides: plan.spec_merges.map((item, index) => ({ gk: item.gk, value: specValues[`s-${index}`] })).filter((item, index) => item.value !== (plan.spec_merges[index].default || "")),
  } : null;
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="采购数据表" description="包装方案、采购量核算表或组托辅材，可多选。" value={paths} onChange={(next) => { setPaths(next); setPlan(null); analysis.reset(); task.reset(); }} multiple filters={excelFilters} />
    <section className="fyt-option-card"><div className="fyt-section-heading fyt-compact"><div><h3>核对确认</h3><p>确认工作表、疑似误删行及单位规格归并。</p></div><button className="fyt-secondary-button" disabled={!paths.length || analysis.busy} onClick={() => void analyze()}>{analysis.busy ? "分析中…" : "分析数据"}</button></div>{analysis.error ? <div className="fyt-page-notice error">{analysis.error}</div> : null}
      {plan ? <div className="fyt-review-stack"><div className="fyt-editable-table"><table><thead><tr><th>纳入</th><th>文件</th><th>工作表</th><th>类型</th><th>可信度</th></tr></thead><tbody>{plan.sheets.map((sheet) => <tr key={sheet.id}><td><input type="checkbox" checked={sheetUse[sheet.id] ?? sheet.use} onChange={(event) => setSheetUse({ ...sheetUse, [sheet.id]: event.target.checked })} /></td><td>{sheet.file}</td><td title={sheet.reason}>{sheet.sheet}</td><td>{sheet.kind}</td><td>{sheet.confidence}</td></tr>)}</tbody></table></div>
        {plan.held_index.length ? <div className="fyt-review-list"><strong>疑似误删行 · {plan.held_index.length}</strong>{plan.held_index.map((item) => { const key = `${item.sid}:${item.ridx}`; return <label key={key}><input type="checkbox" checked={Boolean(held[key])} onChange={(event) => setHeld({ ...held, [key]: event.target.checked })} /><span>{item.sheet || item.sid} · {item.summary || reviewValue(item.rec)}</span></label>; })}</div> : null}
        {[{ title: "单位冲突", items: plan.unit_conflicts, prefix: "u", values: unitValues, setValues: setUnitValues }, { title: "规格归并", items: plan.spec_merges, prefix: "s", values: specValues, setValues: setSpecValues }].map((group) => group.items.length ? <div className="fyt-review-list" key={group.title}><strong>{group.title} · {group.items.length}</strong>{group.items.map((item, index) => { const key = `${group.prefix}-${index}`; const candidates = Object.keys(item.dist || item.variants || {}); return <label key={key}><span>{item.name || item.code || "未命名物料"}</span><select value={group.values[key] || ""} onChange={(event) => group.setValues({ ...group.values, [key]: event.target.value })}>{Array.from(new Set([item.default || "", ...candidates])).map((value) => <option key={value} value={value}>{value || "（空）"}</option>)}</select></label>; })}</div> : null)}</div> : <p className="fyt-empty-message">可先分析后复核，也可直接按默认规则生成。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={paths.length > 0} runLabel="生成透视表" onRun={() => void task.run("pivot.run", { paths, choices })} outDir={task.outDir} outputPath={task.result?.out}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>分组 {task.result.groups} 项 · 合计 {task.result.total}</strong><span>可信度 {task.result.level} · {task.result.score}/100</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface PurchaseResult { out_dir: string; report: string; pairs: unknown[]; matched1: boolean[]; matched2: boolean[]; qty_conflicts: unknown[]; }

/** 对比我方与供应商采购明细，支持分别选择工作表和设置报告中的双方名称。 */
export function PurchasePage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [name1, setName1] = useState("我方");
  const [name2, setName2] = useState("供方");
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const task = useBridgeTask<PurchaseResult>();
  // 匹配数组与原数据逐行对应，未匹配数等于总行数减去布尔真值数量。
  const unmatched1 = task.result ? task.result.matched1.length - task.result.matched1.filter(Boolean).length : 0;
  const unmatched2 = task.result ? task.result.matched2.length - task.result.matched2.filter(Boolean).length : 0;
  const changeFile1 = (next: string[]) => { setFile1(next); setSheet1(""); task.reset(); };
  const changeFile2 = (next: string[]) => { setFile2(next); setSheet2(""); task.reset(); };
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="我方对账单" description="我方导出的采购或对账明细。" value={file1} onChange={changeFile1} filters={excelFilters} /><SheetSelect label="我方工作表" sheets={sheets1} value={sheet1} onChange={(next) => { setSheet1(next); task.reset(); }} />
    <FilePickerField label="供应商对单明细" description="供应商发来的对单明细。" value={file2} onChange={changeFile2} filters={excelFilters} /><SheetSelect label="供方工作表" sheets={sheets2} value={sheet2} onChange={(next) => { setSheet2(next); task.reset(); }} />
    <section className="fyt-option-card"><h3>双方显示名称</h3><div className="fyt-form-grid"><FieldRow label="我方"><input value={name1} onChange={(event) => setName1(event.target.value)} /></FieldRow><FieldRow label="供方"><input value={name2} onChange={(event) => setName2(event.target.value)} /></FieldRow></div></section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(file1.length && file2.length)} runLabel="开始对账" onRun={() => void task.run("purchase.run", { file1, file2, sheet1, sheet2, name1, name2 })} outDir={task.outDir} outputPath={task.result?.report}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>配对 {task.result.pairs.length} 对 · 数量疑点 {task.result.qty_conflicts.length}</strong><span>未对上：{name1} {unmatched1} 条 / {name2} {unmatched2} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface DeliveryResult { plan_path: string; out_dir: string; rows: number; matched: number; missing: unknown[]; order_type: string; case_hit: number; case_used: boolean; supplier_used: boolean; }

/**
 * 根据物料清单生成 SUB 或 KD 送货计划，可选供应商明细和历史计划补全相关字段。
 * 预检只报告可识别性，不会替代正式生成，也不允许绕过核心层校验。
 */
export function DeliveryPage() {
  const [file1, setFile1] = useState<string[]>([]);
  const [file2, setFile2] = useState<string[]>([]);
  const [refPlan, setRefPlan] = useState<string[]>([]);
  const [sheet1, setSheet1] = useState("");
  const [sheet2, setSheet2] = useState("");
  const [orderType, setOrderType] = useState("SUB");
  const sheets1 = useSheets(file1[0] || "");
  const sheets2 = useSheets(file2[0] || "");
  const analysis = useBridgeAction<{ ok: boolean; header_row?: number; n_rows?: number; source?: string; error?: string }>();
  const task = useBridgeTask<DeliveryResult>();
  const changePrimary = (next: string[]) => { setFile1(next); setSheet1(""); analysis.reset(); task.reset(); };
  const changeSupplier = (next: string[]) => { setFile2(next); setSheet2(""); analysis.reset(); task.reset(); };
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="物料清单" description="含物料号与需求数量的主表。" value={file1} onChange={changePrimary} filters={excelFilters} /><SheetSelect label="物料清单工作表" sheets={sheets1} value={sheet1} onChange={(next) => { setSheet1(next); analysis.reset(); task.reset(); }} />
    <FilePickerField label="供应商明细" description="按物料号带出供应商代码与名称；不选则留空。" value={file2} onChange={changeSupplier} optional filters={excelFilters} /><SheetSelect label="供应商工作表" sheets={sheets2} value={sheet2} onChange={(next) => { setSheet2(next); task.reset(); }} />
    <FilePickerField label="参考送货计划" description="可按物料编码带出 CASE、托数和班组。" value={refPlan} onChange={(next) => { setRefPlan(next); task.reset(); }} optional filters={excelFilters} />
    <section className="fyt-option-card"><div className="fyt-segmented fyt-compact"><button className={orderType === "SUB" ? "active" : ""} onClick={() => setOrderType("SUB")}>SUB 订单</button><button className={orderType === "KD" ? "active" : ""} onClick={() => setOrderType("KD")}>KD 订单</button></div><button className="fyt-text-button" disabled={!file1.length || analysis.busy} onClick={() => void analysis.run("delivery.analyze", { path: file1, sheet: sheet1 })}>{analysis.busy ? "预检中…" : "预检物料清单"}</button>{analysis.result ? <div className={`fyt-page-notice ${analysis.result.ok ? "success" : "error"}`}>{analysis.result.ok ? `识别成功：共约 ${analysis.result.n_rows} 行数据。` : analysis.result.error}</div> : null}{analysis.error ? <div className="fyt-page-notice error">{analysis.error}</div> : null}</section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={file1.length > 0} runLabel="生成送货计划" onRun={() => void task.run("delivery.run", { file1, file2, ref_plan: refPlan, sheet1, sheet2, order_type: orderType })} outDir={task.outDir} outputPath={task.result?.plan_path}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>{task.result.order_type} · {task.result.rows} 行 · 供应商匹配 {task.result.matched}</strong><span>未匹配 {task.result.missing.length} · CASE/班组 {task.result.case_used ? `${task.result.case_hit} 行` : "未使用"}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface SupplierBatchSupplier { name: string; rows: number; batches: Array<{ batch: string; rows: number }>; }
interface SupplierBatchPlan { suppliers: SupplierBatchSupplier[]; batches: Array<{ batch: string; file: string; sheet: string; rows: number }>; excluded_original_count: number; unmatched_count: number; }
interface SupplierBatchResult { out_dir: string; files: string[]; suppliers: string[]; batch_dates: Record<string, string>; generated: number; rows: number; excluded_original_count: number; unmatched_count: number; }

interface PurchasePlanResult { out_dir: string; files: string[]; generated: number; rows: number; excluded_original_count: number; new_materials?: string[]; new_suppliers?: string[]; }
interface PurchaseDiffResult { out_dir: string; path: string; rows: number; excluded_original_count: number; }

/** 在同一页提供采购计划生成和辅料实收差异检查，两项任务状态彼此独立。 */
export function PurchasePlanPage() {
  const [templatePaths, setTemplatePaths] = useState<string[]>([]);
  const [batchPaths, setBatchPaths] = useState<string[]>([]);
  const [diffPaths, setDiffPaths] = useState<string[]>([]);
  const task = useBridgeTask<PurchasePlanResult>();
  const diffTask = useBridgeTask<PurchaseDiffResult>();
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="采购计划模板" description="包含供应商代码子表的模板文件，输出按该模板生成；模板中已填写的仓库编号、采购员编号与预计到货日期会原样保留。" value={templatePaths} onChange={(next) => { setTemplatePaths(next); task.reset(); }} filters={excelFilters} />
    <FilePickerField label="辅料清单总表" description="可多选，每个文件按批次号（如 26036-02）生成一个采购计划。" value={batchPaths} onChange={(next) => { setBatchPaths(next); task.reset(); }} multiple filters={excelFilters} />
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(templatePaths.length && batchPaths.length)} runLabel="生成采购计划" onRun={() => void task.run("purchase_plan.run", { template_paths: templatePaths, batch_paths: batchPaths })} outDir={task.outDir} outputPath={task.result?.files?.[0]}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>已生成 {task.result.generated} 个批次采购计划、共 {task.result.rows} 行</strong><span>已排除“原厂” {task.result.excluded_original_count} 条{task.result.new_materials?.length || task.result.new_suppliers?.length ? ` · 档案新增材料 ${task.result.new_materials?.length || 0} 个、供应商 ${task.result.new_suppliers?.length || 0} 家` : ""}</span></ResultSummary> : null}
    </TaskPanel>
    <FilePickerField label="辅料清单总表（差异检查）" description="可多选，提取清单中实收与计划数量不一致的记录，生成差异清单。" value={diffPaths} onChange={(next) => { setDiffPaths(next); diffTask.reset(); }} multiple filters={excelFilters} />
    <TaskPanel busy={diffTask.busy} error={diffTask.error} logs={diffTask.logs} progress={diffTask.progress} onCancel={() => void diffTask.cancel()} canRun={Boolean(diffPaths.length)} runLabel="生成差异清单" onRun={() => void diffTask.run("purchase_plan.diff", { batch_paths: diffPaths })} outDir={diffTask.outDir} outputPath={diffTask.result?.path}>
      {diffTask.presentation ? <BusinessResultView presentation={diffTask.presentation} /> : diffTask.result ? <ResultSummary><strong>已生成差异清单 {diffTask.result.rows} 条</strong><span>已排除“原厂” {diffTask.result.excluded_original_count} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

/**
 * 扫描批次清单得到真实供应商和批次集合，要求逐批填写交付日期并选择输出供应商。
 * “原厂”排除和供应商归属均由核心分析结果决定，页面不自行按文本猜测。
 */
export function SupplierBatchPage() {
  const [batchPaths, setBatchPaths] = useState<string[]>([]);
  const [historyPaths, setHistoryPaths] = useState<string[]>([]);
  const [plan, setPlan] = useState<SupplierBatchPlan | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [batchDates, setBatchDates] = useState<Record<string, string>>({});
  const analysis = useBridgeAction<SupplierBatchPlan>();
  const task = useBridgeTask<SupplierBatchResult>();
  // 任一输入文件变化都可能改变批次和供应商集合，旧计划及日期必须整体作废。
  const reset = () => { setPlan(null); setSelected({}); setBatchDates({}); analysis.reset(); task.reset(); };

  /** 获取供应商与批次分析结果，默认选中全部供应商，但不猜测任何交付日期。 */
  async function analyze() {
    const result = await analysis.run("supplier_batch.analyze", { batch_paths: batchPaths, history_paths: historyPaths });
    if (result) {
      setPlan(result);
      setSelected(Object.fromEntries(result.suppliers.map((item) => [item.name, true])));
      setBatchDates(Object.fromEntries(result.batches.map((item) => [item.batch, ""])));
    }
  }
  /** 按当前计划一次性全选或清空供应商，不引入计划之外的名称。 */
  function chooseAll(value: boolean) {
    setSelected(Object.fromEntries((plan?.suppliers || []).map((item) => [item.name, value])));
  }
  const selectedSuppliers = (plan?.suppliers || []).filter((item) => selected[item.name]).map((item) => item.name);
  // 所有识别批次都填写非空日期后才可执行，避免输出表出现未核对交付日期。
  const missingDateCount = (plan?.batches || []).filter((item) => !batchDates[item.batch]?.trim()).length;
  const deliveryDates = Object.fromEntries((plan?.batches || []).map((item) => [item.batch, batchDates[item.batch]?.trim() || ""]));
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="当前批次清单" description="可多选辅料清单总表，系统自动识别批次和供应商。" value={batchPaths} onChange={(next) => { setBatchPaths(next); reset(); }} multiple filters={excelFilters} />
    <FilePickerField label="历史供应商明细" description="可选，用于补充当前批次清单中缺失的供应商归属。" value={historyPaths} onChange={(next) => { setHistoryPaths(next); reset(); }} multiple optional filters={excelFilters} />
    <section className="fyt-option-card"><div className="fyt-section-heading fyt-compact"><div><h3>核对确认</h3><p>扫描批次后填写交付日期，再选择需要制作的供应商批次表。</p></div><button className="fyt-secondary-button" disabled={!batchPaths.length || analysis.busy} onClick={() => void analyze()}>{analysis.busy ? "扫描中…" : "扫描批次"}</button></div>
      {analysis.error ? <div className="fyt-page-notice error">{analysis.error}</div> : null}
      {plan ? <><div className="fyt-review-section-title"><strong>批次交付日期</strong><span>{missingDateCount ? `还有 ${missingDateCount} 个未填写` : "已全部填写"}</span></div><div className="fyt-batch-date-list">{plan.batches.map((item) => <label key={item.batch}><span><strong>{item.batch}</strong><small>{item.file} · {item.rows} 行</small></span><input type="text" maxLength={50} value={batchDates[item.batch] || ""} placeholder="例如：8.7" aria-label={`${item.batch}交付日期`} onChange={(event) => setBatchDates((current) => ({ ...current, [item.batch]: event.target.value }))} /></label>)}</div><div className="fyt-review-toolbar"><strong>识别到 {plan.suppliers.length} 家供应商</strong><span>已选择 {selectedSuppliers.length} 家</span><div><button className="fyt-text-button" type="button" onClick={() => chooseAll(true)}>全选</button><button className="fyt-text-button" type="button" onClick={() => chooseAll(false)}>清空</button></div></div><div className="fyt-review-list">{plan.suppliers.map((item) => <label key={item.name}><input type="checkbox" checked={Boolean(selected[item.name])} onChange={(event) => setSelected((current) => ({ ...current, [item.name]: event.target.checked }))} /><span><strong>{item.name}</strong><small>{item.rows} 行 · {item.batches.map((batch) => `${batch.batch} ${batch.rows} 行`).join("、")}</small></span></label>)}</div><div className="fyt-page-notice success">批次 {plan.batches.length} 个 · 已排除“原厂” {plan.excluded_original_count} 条 · 未匹配供应商 {plan.unmatched_count} 条。</div></> : <p className="fyt-empty-message">选择当前批次清单后扫描批次。</p>}
    </section>
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(plan && selectedSuppliers.length && missingDateCount === 0)} runLabel="确认并生成供应商批次表" onRun={() => void task.run("supplier_batch.run", { batch_paths: batchPaths, history_paths: historyPaths, choices: { suppliers: selectedSuppliers, batch_dates: deliveryDates } })} outDir={task.outDir} outputPath={task.result?.files?.[0]}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>已生成 {task.result.generated} 家供应商、{task.result.rows} 行明细</strong><span>已排除“原厂” {task.result.excluded_original_count} 条</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface AttendanceArchiveResult { out_dir: string; path: string; month: string; persons: number; days: number; }

/** 汇总多份已填考勤表，生成按人员和每日明细组织的月度归档。 */
export function AttendanceArchivePage() {
  const [paths, setPaths] = useState<string[]>([]);
  const task = useBridgeTask<AttendanceArchiveResult>();
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="考勤填报表" description="可多选本月已填写的考勤表（支持多种表头写法），自动按姓名汇总出勤天数、工时、加班与异常。" value={paths} onChange={(next) => { setPaths(next); task.reset(); }} multiple filters={excelFilters} />
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(paths.length)} runLabel="生成月度汇总" onRun={() => void task.run("attendance_archive.run", { paths })} outDir={task.outDir} outputPath={task.result?.path}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>{task.result.month} 归档完成：{task.result.persons} 人 · {task.result.days} 条出勤记录</strong><span>汇总表已生成，含月度汇总与每日明细两张工作表。</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface ScanBatchInfo { batch: string; sheet: string; rows: number; excluded_rows: number; }
interface ScanFileInfo { name: string; path: string; supplier: string | null; batches: ScanBatchInfo[]; }
interface ReconcileStatementResult { files: Array<{ path: string; name: string; supplier: string; month: string; rows: number }>; total_rows: number; }

/**
 * 先扫描采购清单的供应商和批次，再让用户选择批次、补充未识别供应商并生成对账单。
 * 选择键使用“文件序号：批次号”，可区分不同文件中的同名批次。
 */
export function ReconcileStatementPage() {
  const [paths, setPaths] = useState<string[]>([]);
  const [scanResult, setScanResult] = useState<ScanFileInfo[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [month, setMonth] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const task = useBridgeTask<ReconcileStatementResult>();

  /** 清空旧选择后重新扫描当前文件，避免新结果混入上一批次集合。 */
  async function doScan() {
    if (!paths.length) return;
    setScanning(true); setScanError(""); setScanResult(null); setSelected(new Set());
    try {
      const data = await bridgeRequest<{ files: ScanFileInfo[] }>("reconcile_statement.scan", { paths });
      setScanResult(data.files);
    } catch (reason) { setScanError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setScanning(false); }
  }
  /** 通过复制 Set 切换批次选择，使 React 能可靠检测状态变化。 */
  function toggle(key: string) {
    setSelected((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  }
  /** 将以零为起点的界面行覆盖转换为核心协议使用的一起始文件编号。 */
  function run() {
    const supplierMap: Record<string, string> = {};
    scanResult?.forEach((_, index) => {
      const value = (overrides[String(index)] || "").trim();
      if (value) supplierMap[String(index + 1)] = value; // 核心扫描结果按文件出现顺序使用一起始编号。
    });
    void task.run("reconcile_statement.build", { paths, selected: [...selected], month, supplier_map: supplierMap });
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="采购清单文件" description="上传各供应商的采购清单明细（可多选），扫描后勾选批次生成对账单。" value={paths} onChange={(next) => { setPaths(next); setScanResult(null); setSelected(new Set()); task.reset(); }} multiple filters={excelFilters} />
    <div className="fyt-scan-actions"><button className="fyt-outline-button" disabled={!paths.length || scanning} onClick={() => void doScan()}>{scanning ? "正在扫描批次..." : "扫描批次"}</button>{scanError ? <span className="form-error">{scanError}</span> : null}</div>
    {scanResult ? <div className="fyt-scan-batches">
      {scanResult.map((file, index) => <div className="fyt-scan-file" key={file.name}>
        <div className="fyt-scan-file-head"><strong>{file.name}</strong>{file.supplier ? <span className="fyt-scan-supplier">供应商：<b>{file.supplier}</b></span> : <span className="fyt-scan-supplier">供应商：<input className="fyt-mini-input" placeholder="未识别，请填写" value={overrides[String(index)] || ""} onChange={(event) => setOverrides({ ...overrides, [String(index)]: event.target.value })} /></span>}</div>
        <div className="fyt-scan-batch-list">{file.batches.map((batch) => {
          const key = `${index + 1}:${batch.batch}`;
          return <label className={`fyt-scan-batch ${selected.has(key) ? "checked" : ""}`} key={key}><input type="checkbox" checked={selected.has(key)} onChange={() => toggle(key)} /><span><strong>{batch.batch}</strong><small>{batch.sheet} · {batch.rows} 行{batch.excluded_rows ? ` · 排除标黄 ${batch.excluded_rows} 行` : ""}</small></span></label>;
        })}</div>
      </div>)}
      <div className="fyt-scan-actions"><label className="fyt-month-field">月份（如 202607）<input value={month} onChange={(event) => setMonth(event.target.value)} placeholder="202607" /></label><span className="fyt-scan-count">{selected.size} 个批次已选</span></div>
    </div> : null}
    <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={Boolean(paths.length && selected.size && month.trim())} runLabel="生成对账单" onRun={run} outDir={task.outDir} outputPath={task.result?.files?.[0]?.path}>
      {task.presentation ? <BusinessResultView presentation={task.presentation} /> : task.result ? <ResultSummary><strong>已生成 {task.result.files.length} 份对账单，共 {task.result.total_rows} 行</strong><span>{task.result.files.map((file) => file.name).join("、")}</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}

interface InvoiceItem { path: string; num: string; date: string; seller: string; amount: number | null; tax: number | null; total: number | null; rate: string; item_seed: string; note_seed: string; special: boolean; }
interface InvoiceScan { invoices: InvoiceItem[]; suspects: Array<[string, string]>; suggested_month: string; }
interface InvoiceResult { xlsx: string; review_dir: string; out_dir: string; count: number; suspects: number; }
interface InvoiceMatchResult { out_dir: string; path: string; matched: number; no_invoice: number; no_purchase: number; }

/**
 * 提供发票目录扫描、专票人工复核、月度台账生成和票货匹配两个相互独立流程。
 * 扫描结果是生成台账的只读依据；用户只能选择纳入项并修正费用项目与备注。
 */
export function InvoicePage() {
  const [root, setRoot] = useState<string[]>([]);
  const [month, setMonth] = useState("");
  const [invoiceFiles, setInvoiceFiles] = useState<string[]>([]);
  const [purchaseFiles, setPurchaseFiles] = useState<string[]>([]);
  const matchTask = useBridgeTask<InvoiceMatchResult>();
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [edits, setEdits] = useState<Record<string, { item: string; note: string }>>({});
  const scanTask = useBridgeTask<InvoiceScan>();
  const generateTask = useBridgeTask<InvoiceResult>();
  // 专票筛选仅在扫描结果变化时重算，表格编辑不会重复遍历全部发票。
  const specials = useMemo(() => (scanTask.result?.invoices || []).filter((item) => item.special), [scanTask.result]);

  /** 扫描目录，并用核心建议初始化月份、专票勾选状态和可编辑文本。 */
  async function scan() {
    generateTask.reset();
    const result = await scanTask.run("invoice.scan", { root: root[0] });
    if (!result) return;
    setMonth(result.suggested_month || "");
    setSelected(Object.fromEntries(result.invoices.filter((item) => item.special).map((item) => [item.num, true])));
    setEdits(Object.fromEntries(result.invoices.map((item) => [item.num, { item: item.item_seed || "", note: item.note_seed || "" }])));
  }
  // 生成请求只包含被人工勾选的专票，并合并当前编辑值，不直接修改原扫描对象。
  const rows = specials.filter((invoice) => selected[invoice.num]).map((invoice) => ({ num: invoice.num, date: invoice.date, seller: invoice.seller, item: edits[invoice.num]?.item || "", amount: invoice.amount, tax: invoice.tax, total: invoice.total, rate: invoice.rate, note: edits[invoice.num]?.note || "" }));
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-feature-form">
    <FilePickerField label="资料文件夹" description="递归扫描其中全部 PDF，自动识别增值税专用发票。" value={root} onChange={(next) => { setRoot(next); setMonth(""); setSelected({}); setEdits({}); scanTask.reset(); generateTask.reset(); }} directory />
    <section className="fyt-option-card"><div className="fyt-section-heading fyt-compact"><div><h3>扫描与复核</h3><p>扫描后逐张勾选，并可修正费用项目与备注。</p></div><div className="fyt-toolbar-controls">{scanTask.busy ? <button className="fyt-secondary-button fyt-danger-button" onClick={() => void scanTask.cancel()}>取消扫描</button> : null}<button className="fyt-secondary-button" disabled={!root.length || scanTask.busy} onClick={() => void scan()}>{scanTask.busy ? "扫描中…" : "扫描识别发票"}</button></div></div>{scanTask.busy ? <div className="fyt-task-progress"><i style={{ width: `${Math.max(2, scanTask.progress ?? 4)}%` }} /></div> : null}{scanTask.error ? <div className="fyt-page-notice error">{scanTask.error}</div> : null}{scanTask.logs.length && scanTask.error ? <details className="fyt-task-log"><summary>查看处理提示 · {scanTask.logs.length} 条</summary><pre>{scanTask.logs.join("\n")}</pre></details> : null}
      {specials.length ? <><FieldRow label="统计月份"><input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></FieldRow><div className="fyt-editable-table"><table><thead><tr><th>纳入</th><th>发票号码</th><th>日期</th><th>销售方</th><th>金额</th><th>费用项目</th><th>备注</th></tr></thead><tbody>{specials.map((invoice) => <tr key={invoice.num}><td><input type="checkbox" checked={Boolean(selected[invoice.num])} onChange={(event) => setSelected({ ...selected, [invoice.num]: event.target.checked })} /></td><td>{invoice.num}</td><td>{invoice.date}</td><td>{invoice.seller}</td><td>{invoice.total ?? "—"}</td><td><input value={edits[invoice.num]?.item || ""} onChange={(event) => setEdits({ ...edits, [invoice.num]: { ...edits[invoice.num], item: event.target.value } })} /></td><td><input value={edits[invoice.num]?.note || ""} onChange={(event) => setEdits({ ...edits, [invoice.num]: { ...edits[invoice.num], note: event.target.value } })} /></td></tr>)}</tbody></table></div>{scanTask.result?.suspects.length ? <div className="fyt-page-notice warning">另有 {scanTask.result.suspects.length} 项存疑，将写入复核清单。</div> : null}</> : scanTask.result ? <div className="fyt-page-notice error">未识别到增值税专用发票。</div> : null}
    </section>
    <TaskPanel busy={generateTask.busy} error={generateTask.error} logs={generateTask.logs} progress={generateTask.progress} onCancel={() => void generateTask.cancel()} canRun={Boolean(scanTask.result && rows.length && month)} runLabel="生成月度台账" onRun={() => void generateTask.run("invoice.generate", { scan: scanTask.result, rows, month })} outDir={generateTask.outDir} outputPath={generateTask.result?.xlsx}>
      {generateTask.presentation ? <BusinessResultView presentation={generateTask.presentation} /> : generateTask.result ? <ResultSummary><strong>已归档 {generateTask.result.count} 张专用发票</strong><span>存疑 {generateTask.result.suspects} 项</span></ResultSummary> : null}
    </TaskPanel>
    <FilePickerField label="发票台账" description="选择发票统计生成的月度台账，读取“销售方名称”与“价税合计”。" value={invoiceFiles} onChange={(next) => { setInvoiceFiles(next); matchTask.reset(); }} multiple filters={excelFilters} />
    <FilePickerField label="采购明细" description="选择供应商批次表或采购计划导入输出，读取“供应商”列。" value={purchaseFiles} onChange={(next) => { setPurchaseFiles(next); matchTask.reset(); }} multiple filters={excelFilters} />
    <TaskPanel busy={matchTask.busy} error={matchTask.error} logs={matchTask.logs} progress={matchTask.progress} onCancel={() => void matchTask.cancel()} canRun={Boolean(invoiceFiles.length && purchaseFiles.length)} runLabel="开始票货匹配" onRun={() => void matchTask.run("invoice_match.run", { invoice_paths: invoiceFiles, purchase_paths: purchaseFiles })} outDir={matchTask.outDir} outputPath={matchTask.result?.path}>
      {matchTask.presentation ? <BusinessResultView presentation={matchTask.presentation} /> : matchTask.result ? <ResultSummary><strong>正常 {matchTask.result.matched} 家 · 无票采购 {matchTask.result.no_invoice} 家 · 有发票无采购 {matchTask.result.no_purchase} 家</strong><span>结果文件已生成，详见匹配表。</span></ResultSummary> : null}
    </TaskPanel>
  </section></div>;
}
