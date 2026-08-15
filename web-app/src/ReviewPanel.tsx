/**
 * Web 两阶段业务的人工复核界面集合。
 *
 * 各面板只根据只读分析计划收集明确选择，再交给任务复核接口继续执行；
 * 不在前端重新识别表头、发票、供应商或冲突，也不提供绕过确认的执行入口。
 */
import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import Button from "./ui/Button";
import FormField from "./ui/FormField";
import "./workflows.css";

/** 支持人工复核的业务功能键，与工作区 SPECS 中的 reviewAction 类型保持一致。 */
type ReviewKind = "reconcile" | "pivot" | "invoice" | "compare" | "supplier_batch";
/** 复核面板公共入参：功能类型、只读分析计划、确认回调和提交锁。 */
type ReviewPanelProps = {
  kind: ReviewKind;
  result: unknown;
  onConfirm: (choices: Record<string, unknown>) => void;
  busy?: boolean;
};

/** 兼容历史任务结果外层可能存在的 `result` 包装，并为异常结构返回空对象。 */
function unwrap(value: unknown): Record<string, any> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  return record.result && typeof record.result === "object" ? record.result as Record<string, any> : record as Record<string, any>;
}

/** 把计划中的嵌套记录压缩为复核列表可读文本，不修改原始值。 */
function reviewValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(reviewValue).join("、");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}：${reviewValue(item)}`)
      .join("；");
  }
  return String(value);
}

/** 统一复核标题、说明、内容区和确认按钮；具体面板负责覆盖实际确认载荷。 */
function ReviewShell({ title, description, onConfirm, busy, confirmDisabled, children, actionLabel }: ReviewPanelProps & { title: string; description: string; actionLabel: string; confirmDisabled?: boolean; children: ReactNode }) {
  return <section className="fyt-review-panel">
    <div className="fyt-review-head"><div><span className="fyt-eyebrow">请确认</span><h2>{title}</h2><p>{description}</p></div><span className="fyt-review-mark"><Icon name="check" size={17} /></span></div>
    <div className="fyt-review-body">{children}</div>
    <div className="fyt-review-actions"><span>确认后将继续执行并生成结果文件</span><Button variant="primary" type="button" disabled={busy || confirmDisabled} loading={busy} onClick={() => onConfirm({})}>{busy ? "正在提交" : actionLabel}<Icon name="arrow" size={16} /></Button></div>
  </section>;
}

/** 工时对账只读分析计划：目标表结构与两侧姓名匹配候选。 */
type ReconcilePlan = { target: { file: string; sheet: string; sheets?: string[]; name_col?: number; comp_col?: number; work_col?: number }; only_labor?: string[]; only_zong?: string[]; sources?: Array<Record<string, unknown>>; labor?: Array<Record<string, unknown>> };

/** 复核目标表工作表、列角色和两侧姓名配对，只提交相对分析默认值发生变化的覆盖项。 */
function ReconcileReview({ plan, onConfirm, busy }: { plan: ReconcilePlan; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const target = plan.target || { file: "", sheet: "" };
  const [sheet, setSheet] = useState(target.sheet || "");
  const [roles, setRoles] = useState<Record<string, number>>({ name: target.name_col || 0, comp: target.comp_col || 0, work: target.work_col || 0 });
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const candidates = plan.only_zong || [];
  // 列选择范围至少二十列，并在识别列后预留十列，同时限制为六十列避免下拉项过长。
  const upper = Math.max(20, Math.min(60, Math.max(target.name_col || 0, target.comp_col || 0, target.work_col || 0) + 10));
  const choices = () => ({
    target_sheet: sheet && sheet !== target.sheet ? sheet : null,
    target_roles: Object.fromEntries(Object.entries(roles).filter(([key, value]) => value && value !== (target as Record<string, any>)[`${key}_col`])),
    aliases: Object.fromEntries(Object.entries(aliases).filter(([, value]) => value.trim())),
    save_mapping: true,
  });
  return <ReviewShell kind="reconcile" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="工时对账确认" description="确认目标表结构和姓名配对后，再生成对账结果。" actionLabel="按此对账">
    <div className="fyt-review-block"><div className="fyt-review-block-title">目标表结构</div><div className="fyt-review-form-grid"><label>文件<strong>{target.file}</strong></label><label>工作表<select value={sheet} onChange={(event) => setSheet(event.target.value)}>{(target.sheets || [target.sheet]).map((item) => <option value={item} key={item}>{item}</option>)}</select></label>{[["name", "姓名列"], ["comp", "所属公司列"], ["work", "出勤工时列"]].map(([key, label]) => <label key={key}>{label}<select value={String(roles[key])} onChange={(event) => setRoles((current) => ({ ...current, [key]: Number(event.target.value) }))}><option value="0">自动识别</option>{Array.from({ length: upper }, (_, index) => index + 1).map((column) => <option value={column} key={column}>第 {column} 列</option>)}</select></label>)}</div></div>
    <div className="fyt-review-block"><div className="fyt-review-block-title">姓名匹配 <span>{(plan.only_labor || []).length} 项待确认</span></div>{plan.only_labor?.length ? <div className="fyt-review-list">{plan.only_labor.map((name) => <label key={name}><span>{name}</span><select value={aliases[name] || ""} onChange={(event) => setAliases((current) => ({ ...current, [name]: event.target.value }))}><option value="">不配对</option>{candidates.map((candidate) => <option value={candidate} key={candidate}>{candidate}</option>)}</select></label>)}</div> : <p className="fyt-review-empty">两侧姓名已全部匹配，无需手动配对。</p>}</div>
    <div className="fyt-review-block fyt-review-readonly"><div className="fyt-review-block-title">识别概况</div><p>数据来源 {plan.sources?.length || 0} 份，对账单 {plan.labor?.length || 0} 份；仅我司有 {plan.only_zong?.length || 0} 人。</p></div>
  </ReviewShell>;
}

/** 销售透视只读分析计划：工作表纳入范围、疑似误删行和单位/规格归并候选。 */
type PivotPlan = { sheets?: Array<{ id: number | string; file: string; sheet: string; use: boolean; kind: string; confidence: number; reason?: string }>; held_index?: Array<{ sid: number | string; ridx: number; file?: string; sheet?: string; rec?: unknown }>; unit_conflicts?: Array<{ gk: unknown; default?: string; dist?: Record<string, number>; name?: string; code?: string; spec?: string }>; spec_merges?: Array<{ gk: unknown; default?: string; variants?: Record<string, number>; name?: string; code?: string }> };

/** 复核透视表纳入范围、疑似误删行以及单位和规格冲突。 */
function PivotReview({ plan, onConfirm, busy }: { plan: PivotPlan; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const sheets = plan.sheets || [];
  const held = plan.held_index || [];
  const units = plan.unit_conflicts || [];
  const specs = plan.spec_merges || [];
  const [sheetUse, setSheetUse] = useState<Record<string, boolean>>(() => Object.fromEntries(sheets.map((item) => [String(item.id), item.use])));
  const [heldKeep, setHeldKeep] = useState<Record<string, boolean>>({});
  const [unitValues, setUnitValues] = useState<Record<string, string>>(() => Object.fromEntries(units.map((item, index) => [`${index}`, item.default || ""])));
  const [specValues, setSpecValues] = useState<Record<string, string>>(() => Object.fromEntries(specs.map((item, index) => [`${index}`, item.default || ""])));
  /** 合并系统默认值与全部候选值并去重，确保默认值始终可重新选择。 */
  function options(item: { default?: string; dist?: Record<string, number>; variants?: Record<string, number> }) { return Array.from(new Set([item.default || "", ...Object.keys(item.dist || item.variants || {})])); }

  /** 仅发送相对默认值发生变化的单位和规格覆盖，减少复核载荷。 */
  function choices() {
    return {
      sheets: sheetUse,
      held: held.map((item) => ({ sid: item.sid, ridx: item.ridx, keep: Boolean(heldKeep[`${item.sid}:${item.ridx}`]) })),
      unit_overrides: units.map((item, index) => ({ gk: item.gk, value: unitValues[String(index)] || "" })).filter((item, index) => item.value !== (units[index].default || "")),
      spec_overrides: specs.map((item, index) => ({ gk: item.gk, value: specValues[String(index)] || "" })).filter((item, index) => item.value !== (specs[index].default || "")),
    };
  }
  return <ReviewShell kind="pivot" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="销售透视确认" description="确认工作表、疑似误删行和单位/规格归并后再生成透视表。" actionLabel="按此生成">
    <div className="fyt-review-block"><div className="fyt-review-block-title">工作表纳入 <span>{sheets.length} 张</span></div><div className="fyt-review-table-wrap"><table className="fyt-review-table"><thead><tr><th>纳入</th><th>文件</th><th>工作表</th><th>识别类型</th><th>可信度</th></tr></thead><tbody>{sheets.map((item) => <tr key={`${item.id}`}><td><input type="checkbox" checked={Boolean(sheetUse[String(item.id)])} onChange={(event) => setSheetUse((current) => ({ ...current, [String(item.id)]: event.target.checked }))} /></td><td>{item.file}</td><td title={item.reason}>{item.sheet}</td><td>{item.kind}</td><td>{item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "—"}</td></tr>)}</tbody></table></div></div>
    <div className="fyt-review-block"><div className="fyt-review-block-title">疑似误删行 <span>{held.length} 行</span></div>{held.length ? <div className="fyt-review-list">{held.map((item) => { const key = `${item.sid}:${item.ridx}`; return <label key={key}><input type="checkbox" checked={Boolean(heldKeep[key])} onChange={(event) => setHeldKeep((current) => ({ ...current, [key]: event.target.checked }))} /><span>{item.file || item.sheet || item.sid} · {reviewValue(item.rec)}</span></label>; })}</div> : <p className="fyt-review-empty">没有疑似误删行。</p>}</div>
    <div className="fyt-review-block"><div className="fyt-review-block-title">单位/规格归并 <span>{units.length + specs.length} 项</span></div>{units.concat(specs).length ? <div className="fyt-review-list">{units.map((item, index) => <label key={`unit-${index}`}><span>单位 · {item.name || item.code || "未命名物料"}</span><select value={unitValues[String(index)] || ""} onChange={(event) => setUnitValues((current) => ({ ...current, [String(index)]: event.target.value }))}>{options(item).map((value) => <option value={value} key={value}>{value || "（空）"}</option>)}</select></label>)}{specs.map((item, index) => <label key={`spec-${index}`}><span>规格 · {item.name || item.code || "未命名物料"}</span><select value={specValues[String(index)] || ""} onChange={(event) => setSpecValues((current) => ({ ...current, [String(index)]: event.target.value }))}>{options(item).map((value) => <option value={value} key={value}>{value || "（空）"}</option>)}</select></label>)}</div> : <p className="fyt-review-empty">没有单位冲突或规格归并提示。</p>}</div>
  </ReviewShell>;
}

/** 发票分析计划中的单张识别结果；`item_seed` 与 `note_seed` 是可编辑字段的识别种子。 */
type InvoiceItem = { num?: string; date?: string; seller?: string; item_seed?: string; amount?: number; tax?: number; total?: number; rate?: number | string; note_seed?: string; special?: boolean };
/** 发票复核界面中的可编辑行，额外包含勾选状态。 */
type InvoiceRow = { selected: boolean; num: string; date: string; seller: string; item: string; amount?: number; tax?: number; total?: number; rate?: number | string; note: string; special: boolean };

/** 按月份和发票类型筛选识别结果，允许逐张修正可编辑字段后生成台账。 */
function InvoiceReview({ plan, onConfirm, busy }: { plan: { invoices?: InvoiceItem[]; suggested_month?: string }; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const [month, setMonth] = useState(plan.suggested_month || "");
  const [includeNormal, setIncludeNormal] = useState(false);
  const [rows, setRows] = useState<InvoiceRow[]>(() => (plan.invoices || []).map((item) => ({ selected: Boolean(item.special), num: item.num || "", date: item.date || "", seller: item.seller || "", item: item.item_seed || "", amount: item.amount, tax: item.tax, total: item.total, rate: item.rate, note: item.note_seed || "", special: Boolean(item.special) })));
  // 过滤可能遍历整月发票，仅在记录、月份或类型开关变化时重算。
  const visible = useMemo(() => rows.filter((row) => (includeNormal || row.special) && (!month || row.date.startsWith(month))), [rows, includeNormal, month]);
  /** 以不可变数组更新原始行索引，保留筛选前后的编辑状态。 */
  function patch(index: number, value: Partial<InvoiceRow>) { setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...value } : row)); }
  /** 只提交当前筛选范围内被勾选的行，并移除界面专用状态字段。 */
  function choices() { return { month, include_normal: includeNormal, rows: visible.filter((row) => row.selected).map(({ selected: _selected, special: _special, ...row }) => row) }; }
  return <ReviewShell kind="invoice" result={plan} onConfirm={() => onConfirm(choices())} busy={busy} title="发票逐张复核" description="号码、日期和金额保持识别原值；销售方、费用项目、税率和备注可调整。" actionLabel="生成发票台账">
    <div className="fyt-review-toolbar"><FormField label="统计月份" htmlFor="review-invoice-month"><input id="review-invoice-month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></FormField><label className="fyt-review-check" htmlFor="review-include-normal"><input id="review-include-normal" type="checkbox" checked={includeNormal} onChange={(event) => setIncludeNormal(event.target.checked)} />同时包含普通发票</label><span>当前显示 {visible.length} 张</span></div>
    <div className="fyt-review-table-wrap"><table className="fyt-review-table fyt-review-invoice-table"><thead><tr><th>保留</th><th>发票号码</th><th>日期</th><th>销售方</th><th>费用项目</th><th>不含税</th><th>税额</th><th>合计</th><th>税率</th><th>备注</th></tr></thead><tbody>{visible.map((row) => { const index = rows.indexOf(row); return <tr key={`${row.num}-${row.date}`}><td><input type="checkbox" checked={row.selected} onChange={(event) => patch(index, { selected: event.target.checked })} /></td><td>{row.num}</td><td>{row.date}</td><td><input value={row.seller} onChange={(event) => patch(index, { seller: event.target.value })} /></td><td><input value={row.item} onChange={(event) => patch(index, { item: event.target.value })} /></td><td>{row.amount ?? ""}</td><td>{row.tax ?? ""}</td><td>{row.total ?? ""}</td><td><input value={String(row.rate ?? "")} onChange={(event) => patch(index, { rate: event.target.value })} /></td><td><input value={row.note} onChange={(event) => patch(index, { note: event.target.value })} /></td></tr>; })}</tbody></table></div>
    {!visible.length ? <p className="fyt-review-empty">当前月份或发票类型筛选后没有记录。</p> : null}
  </ReviewShell>;
}

/** 选择表格配对关键列和实际比较列，关键列不会同时出现在比较列集合中。 */
function CompareReview({ plan, onConfirm, busy }: { plan: { headers1?: string[]; headers2?: string[]; common?: string[] }; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const common = plan.common || [];
  const [key, setKey] = useState(common[0] || "");
  const selectable = common.filter((item) => item !== key);
  const [columns, setColumns] = useState<string[]>(() => common.slice(1));
  /** 更换关键列并保留仍合法的比较列；全部失效时默认选择其余公共列。 */
  function changeKey(next: string) {
    setKey(next);
    setColumns((current) => {
      const valid = current.filter((item) => item !== next && common.includes(item));
      return valid.length ? valid : common.filter((item) => item !== next);
    });
  }
  /** 以不可变数组切换单个比较列。 */
  function toggleColumn(column: string) {
    setColumns((current) => current.includes(column) ? current.filter((item) => item !== column) : [...current, column]);
  }
  return <ReviewShell kind="compare" result={plan} onConfirm={() => onConfirm({ key, columns })} busy={busy} confirmDisabled={!key || !columns.length} title="表格比对确认" description="先选择配对关键列，再限定真正需要核对的比较列，减少无关差异。" actionLabel="开始比对">
    <div className="fyt-review-block"><div className="fyt-review-block-title">配对依据</div>{common.length ? <label className="fyt-review-select">关键列<select value={key} onChange={(event) => changeKey(event.target.value)}>{common.map((item) => <option value={item} key={item}>{item}</option>)}</select></label> : <p className="fyt-review-empty">两张表没有公共列，无法进行配对。</p>}<p className="fyt-review-readonly">A 表 {plan.headers1?.length || 0} 列 · B 表 {plan.headers2?.length || 0} 列 · 公共列 {common.length} 个</p></div>
    <div className="fyt-review-block"><div className="fyt-review-block-title"><span>比较列</span><span>已选 {columns.length} 列</span></div>{selectable.length ? <><div className="fyt-review-toolbar"><Button variant="secondary" size="sm" type="button" onClick={() => setColumns(selectable)}>全选</Button><Button variant="secondary" size="sm" type="button" onClick={() => setColumns([])}>清空</Button></div><div className="fyt-review-list">{selectable.map((column) => <label key={column}><input type="checkbox" checked={columns.includes(column)} onChange={() => toggleColumn(column)} /><span>{column}</span></label>)}</div></> : <p className="fyt-review-empty">除关键列外没有其他公共列可比较。</p>}</div>
  </ReviewShell>;
}

/** 供应商批次表分析计划：供应商范围、批次行数、未匹配和排除原厂记录数。 */
type SupplierBatchPlan = {
  suppliers?: Array<{ name: string; rows: number; batches?: Array<{ batch: string; rows: number }> }>;
  batches?: Array<{ batch: string; file: string; sheet: string; rows: number }>;
  unmatched_count?: number;
  excluded_original_count?: number;
};

/** 要求逐批填写交付日期，并选择实际需要生成文件的供应商范围。 */
function SupplierBatchReview({ plan, onConfirm, busy }: { plan: SupplierBatchPlan; onConfirm: (choices: Record<string, unknown>) => void; busy?: boolean }) {
  const suppliers = plan.suppliers || [];
  const batches = plan.batches || [];
  const [selected, setSelected] = useState<Record<string, boolean>>(() => Object.fromEntries(suppliers.map((item) => [item.name, true])));
  const [batchDates, setBatchDates] = useState<Record<string, string>>(() => Object.fromEntries(batches.map((item) => [item.batch, ""])));
  const selectedNames = suppliers.filter((item) => selected[item.name]).map((item) => item.name);
  const missingDateCount = batches.filter((item) => !batchDates[item.batch]?.trim()).length;
  /** 对当前分析计划中的供应商执行全选或清空。 */
  function setAll(value: boolean) {
    setSelected(Object.fromEntries(suppliers.map((item) => [item.name, value])));
  }
  const deliveryDates = Object.fromEntries(batches.map((item) => [item.batch, batchDates[item.batch]?.trim() || ""]));
  return <ReviewShell kind="supplier_batch" result={plan} onConfirm={() => onConfirm({ suppliers: selectedNames, batch_dates: deliveryDates })} busy={busy} confirmDisabled={!selectedNames.length || missingDateCount > 0} title="供应商批次表复核" description="逐批次确认交付日期，再选择需要分别制作采购明细的供应商。名称含“原厂”的材料不会进入结果。" actionLabel="确认并生成">
    <div className="fyt-review-block"><div className="fyt-review-block-title"><span>批次交付日期</span><span>{missingDateCount ? `还有 ${missingDateCount} 个未填写` : "已全部填写"}</span></div>{batches.length ? <div className="fyt-review-date-list">{batches.map((item) => <label key={`${item.batch}-${item.file}`}><span className="fyt-review-date-batch"><small>批次</small><strong>{item.batch || "未命名批次"}</strong><em>{item.file} · {item.rows} 行</em></span><span className="fyt-review-date-field"><small>交付日期</small><input type="text" maxLength={50} value={batchDates[item.batch] || ""} placeholder="例如：8.7" aria-label={`${item.batch || "未命名批次"}交付日期`} onChange={(event) => setBatchDates((current) => ({ ...current, [item.batch]: event.target.value }))} /></span></label>)}</div> : <p className="fyt-review-empty">没有识别到可填写交付日期的批次。</p>}</div>
    <div className="fyt-review-block"><div className="fyt-review-supplier-head"><div><strong>供应商范围</strong><small>识别到 {suppliers.length} 家供应商</small></div><div className="fyt-review-selection"><span>已选择 {selectedNames.length} 家</span><div><Button variant="secondary" size="sm" type="button" onClick={() => setAll(true)}>全选</Button><Button variant="secondary" size="sm" type="button" onClick={() => setAll(false)}>清空</Button></div></div></div>{suppliers.length ? <div className="fyt-review-list">{suppliers.map((item) => <label key={item.name}><input type="checkbox" checked={Boolean(selected[item.name])} onChange={(event) => setSelected((current) => ({ ...current, [item.name]: event.target.checked }))} /><span><strong>{item.name}</strong><small>{item.rows} 行 · {(item.batches || []).map((batch) => `${batch.batch} ${batch.rows} 行`).join("、")}</small></span></label>)}</div> : <p className="fyt-review-empty">没有识别到可制作的供应商。</p>}</div>
    <div className="fyt-review-block fyt-review-readonly"><div className="fyt-review-block-title">扫描结果</div><p>批次 {plan.batches?.length || 0} 个 · 已排除“原厂” {plan.excluded_original_count || 0} 条 · 未匹配供应商 {plan.unmatched_count || 0} 条。</p></div>
  </ReviewShell>;
}

/** 按功能类型分派专用复核面板，未知类型回退到表格比对复核。 */
export function ReviewPanel({ kind, result, onConfirm, busy }: ReviewPanelProps) {
  const plan = unwrap(result);
  if (kind === "reconcile") return <ReconcileReview plan={plan as ReconcilePlan} onConfirm={onConfirm} busy={busy} />;
  if (kind === "pivot") return <PivotReview plan={plan as PivotPlan} onConfirm={onConfirm} busy={busy} />;
  if (kind === "invoice") return <InvoiceReview plan={plan as { invoices?: InvoiceItem[]; suggested_month?: string }} onConfirm={onConfirm} busy={busy} />;
  if (kind === "supplier_batch") return <SupplierBatchReview plan={plan as SupplierBatchPlan} onConfirm={onConfirm} busy={busy} />;
  return <CompareReview plan={plan as { headers1?: string[]; headers2?: string[]; common?: string[] }} onConfirm={onConfirm} busy={busy} />;
}
