/**
 * 桌面端数据治理页面集合：主数据、报表、批次跟踪、文件数据库、字段映射和模板版本。
 *
 * 页面只维护筛选、选择和编辑草稿；正式数据读写、自动分类、模板规则和删除范围
 * 均由桥接白名单后的核心模块决定，前端不直接修改索引文件或归档副本。
 */
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { FilePickerField, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeTask } from "../hooks/useBridgeTask";
import { bridgeRequest, type LibraryItem, type LibrarySummary } from "../lib/bridge";
import { confirmAction, openLocalPath } from "../lib/files";
import Icon from "../components/Icon";

/** 主数据与报表页面共用的 Excel 文件筛选器。 */
const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls"] }];

/** 主数据完整快照：供应商与材料档案均以核心层返回值为准。 */
type CatalogData = {
  /** 供应商名称到编码的映射。 */
  suppliers: Record<string, string>;
  /** 材料编号到名称、规格、单位、供应商的映射；字段允许缺省。 */
  materials: Record<string, { name?: string; spec?: string; unit?: string; supplier?: string }>;
  /** 主数据最近更新时间。 */
  updated_at: string;
};

/**
 * 维护供应商代码和材料档案，并在每次变更后使用核心层返回的完整主数据快照刷新界面。
 * 搜索只影响当前材料列表显示，不改变正式主数据，也不会把空白字段写成推断值。
 */
export function CatalogPage() {
  const [data, setData] = useState<CatalogData | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [supplierCode, setSupplierCode] = useState("");
  const [materialQuery, setMaterialQuery] = useState("");
  const [materialForm, setMaterialForm] = useState({ code: "", name: "", spec: "", unit: "", supplier: "" });
  /** 重新读取主数据完整快照；使用稳定回调便于挂载效应安全依赖。 */
  const refresh = useCallback(async () => {
    setError("");
    try { setData(await bridgeRequest<CatalogData>("catalog.list")); }  // 每次刷新都以核心层返回为真值，前端不自行推断
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  /** 调用指定主数据变更动作，并以核心层返回的完整快照替换本地数据。 */
  async function mutate(op: string, params: Record<string, string>) {
    setMessage(""); setError("");
    try {
      setData(await bridgeRequest<CatalogData>(`catalog.${op}`, params));  // 以核心返回的完整快照刷新本地状态
      setMessage(op.startsWith("delete") ? "已删除。" : "已保存。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  // 只排序由 Object.entries 创建的新数组，不会改变桥接响应对象中的原始顺序。
  const suppliers = Object.entries(data?.suppliers || {}).sort(([a], [b]) => a.localeCompare(b, "zh-CN"));  // 只排序新数组，不改变桥接响应对象的原始顺序
  const materialQueryLower = materialQuery.trim().toLowerCase();
  const materials = Object.entries(data?.materials || {})
    .filter(([code, item]) => !materialQueryLower || `${code} ${item.name || ""} ${item.supplier || ""}`.toLowerCase().includes(materialQueryLower))  // 搜索只影响当前显示，不改正式主数据
    .sort(([a], [b]) => a.localeCompare(b, "zh-CN"));
  return <div className="fyt-page-flow fyt-wide-flow">
    {error ? <div className="fyt-page-notice error">{error}</div> : null}
    {message ? <div className="fyt-page-notice success">{message}</div> : null}
    <section className="fyt-table-card">
      <div className="fyt-table-toolbar"><div><strong>供应商代码 · {suppliers.length} 条</strong><span>维护供应商名称和代码，后续处理时会自动补全缺失信息。</span></div></div>
      <div className="fyt-inline-fields fyt-data-entry-row">
        <label>供应商名称<input value={supplierName} placeholder="例如：客供件" onChange={(event) => setSupplierName(event.target.value)} /></label>
        <label>供应商编码<input value={supplierCode} placeholder="例如：GYS26062300001" onChange={(event) => setSupplierCode(event.target.value)} /></label>
        <button className="fyt-primary-button" disabled={!supplierName.trim() || !supplierCode.trim()} onClick={() => void mutate("upsert_supplier", { name: supplierName, code: supplierCode }).then(() => { setSupplierName(""); setSupplierCode(""); })}>保存供应商</button>
      </div>
      <div className="fyt-table-scroll">
        <table>
          <thead><tr><th>供应商名称</th><th>供应商编码</th><th>操作</th></tr></thead>
          <tbody>
            {suppliers.map(([name, code]) => <tr key={name}><td><strong>{name}</strong></td><td>{code}</td><td><button className="fyt-text-button fyt-danger-text" onClick={() => void mutate("delete_supplier", { name })}>删除</button></td></tr>)}
            {!suppliers.length ? <tr><td colSpan={3} className="fyt-empty-cell">还没有供应商代码，可在上方添加。</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
    <section className="fyt-table-card">
      <div className="fyt-table-toolbar">
        <div><strong>材料主数据 · {Object.keys(data?.materials || {}).length} 条</strong><span>按材料编号维护名称、规格、单位和供应商，供各业务功能补全数据。</span></div>
        <div className="fyt-toolbar-controls"><input placeholder="搜索编号、名称或供应商" value={materialQuery} onChange={(event) => setMaterialQuery(event.target.value)} /></div>
      </div>
      <div className="fyt-inline-fields fyt-data-entry-row fyt-data-entry-row-divider">
        {(["code", "name", "spec", "unit", "supplier"] as const).map((field) => (
          <label key={field}>{field === "code" ? "材料编号" : field === "name" ? "材料名称" : field === "spec" ? "规格" : field === "unit" ? "单位" : "供应商"}
            <input value={materialForm[field]} placeholder={field === "supplier" ? "例如：众瀚" : ""} onChange={(event) => setMaterialForm((current) => ({ ...current, [field]: event.target.value }))} />
          </label>
        ))}
        <button className="fyt-primary-button" disabled={!materialForm.code.trim()} onClick={() => void mutate("upsert_material", materialForm).then(() => setMaterialForm({ code: "", name: "", spec: "", unit: "", supplier: "" }))}>保存材料</button>
      </div>
      <div className="fyt-table-scroll">
        <table>
          <thead><tr><th>材料编号</th><th>名称</th><th>规格</th><th>单位</th><th>供应商</th><th>操作</th></tr></thead>
          <tbody>
            {materials.map(([code, item]) => <tr key={code}><td><strong>{code}</strong></td><td>{item.name || "—"}</td><td>{item.spec || "—"}</td><td>{item.unit || "—"}</td><td>{item.supplier || "—"}</td><td><button className="fyt-text-button fyt-danger-text" onClick={() => void mutate("delete_material", { code })}>删除</button></td></tr>)}
            {!materials.length ? <tr><td colSpan={6} className="fyt-empty-cell">暂无材料记录</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  </div>;
}

/** 字段映射业务类型键到中文使用场景的展示映射。 */
const ROLE_KIND_LABELS: Record<string, string> = {
  att_source: "填报·系统数据表", att_target: "填报·待填考勤表",
  rec_source: "对账·数据来源", rec_zong: "对账·待对总表", rec_labor: "对账·劳务对账单",
  pivot_source: "透视·数据来源", purchase_ours: "采购·我方数据", purchase_theirs: "采购·供应商数据",
  delivery_material: "送货·物料清单", supplier_batch: "批次·清单", invoice_source: "发票·来源",
  custom: "自定义映射",
};

/** 字段角色键到中文列语义的展示映射。 */
const ROLE_KEY_LABELS: Record<string, string> = {
  name: "姓名", date: "日期", on: "上班1打卡", off: "下班1打卡",
  sys_on: "上班(系统)", act_on: "上班(实际)", sys_off: "下班(系统)", act_off: "下班(实际)",
  rest: "休息时间", work: "实际工时", ot: "加班", comp: "劳务公司",
  check: "对账时间", total: "合计工时",
};

/** 将业务模板类型键映射为中文使用场景，未知扩展类型保留原键。 */
function roleKindLabel(kind: string) {
  return ROLE_KIND_LABELS[kind] || kind;
}

/** 将核心层字段角色键转换为维护人员熟悉的列语义，未知键保留原值便于排查。 */
function roleKeyLabel(key: string) {
  return ROLE_KEY_LABELS[key] || key;
}

/** 按选定时间范围生成任务汇总报表；文件内容与行数均以核心层返回结果为准。 */
export function ReportPage() {
  const [range, setRange] = useState("30d");
  const [result, setResult] = useState<{ path: string; rows: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  /** 清空旧结果后生成新报表，防止生成期间仍展示上一个时间范围的文件。 */
  async function build() {
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await bridgeRequest<{ path: string; rows: number }>("report.build", { range }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-workspace-card">
    <div className="fyt-workspace-intro"><div className="fyt-workspace-icon"><Icon name="pie" size={22} /></div><div><h3>业务报表中心</h3><p>按时间范围汇总各业务模块的任务记录，一键生成可打印的 Excel 报表。</p></div></div>
    <div className="fyt-segmented fyt-report-range">
      {([["7d", "近 7 天"], ["30d", "近 30 天"], ["month", "本月"], ["all", "全部"]] as const).map(([key, label]) => (
        <button key={key} className={range === key ? "active" : ""} onClick={() => setRange(key)}>{label}</button>
      ))}
    </div>
    <div className="fyt-run-strip"><div><strong>报表内容</strong><p>包含任务汇总、模块分布与逐条明细（时间、模块、任务、状态、结果文件数）。</p></div>
      <button className="fyt-primary-button" disabled={busy} onClick={() => void build()}>{busy ? "生成中…" : "生成报表"}</button></div>
    {error ? <div className="fyt-page-notice error">{error}</div> : null}
    {result ? <div className="fyt-page-notice success">已生成 {result.rows} 条任务记录，文件：{result.path}。</div> : null}
  </section></div>;
}

/** 为数据库文件列表转换紧凑大小单位，避免在表格中展示过长字节数。 */
function humanSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 批次跟踪结果中的功能键到中文标题的展示映射。 */
const TRACK_FEATURE_TITLES: Record<string, string> = {
  attendance: "考勤填报", reconcile: "工时对账", arrival: "到料明细", pivot: "销售透视",
  purchase: "采购对账", shipping_review: "发运评审对比", delivery: "送货计划", supplier_batch: "供应商批次表",
  purchase_plan: "采购计划导入", invoice: "发票统计", rename: "批量重命名",
  text: "文本工具", pdf: "PDF 工具", excel: "Excel 工具", compare: "表格比对", currency: "金额大写",
};

/** 将批次跟踪中的任务状态映射为用户语言，未知值原样显示以保留诊断信息。 */
function trackStatusLabel(status: string) {
  const labels: Record<string, string> = { ok: "已完成", running: "处理中", failed: "处理失败", interrupted: "已中断", queued: "等待处理" };
  return labels[status] || status;
}

/**
 * 按批次关键字跨业务任务历史检索处理轨迹。
 * 搜索由核心层统一匹配任务消息和输出信息，页面不读取结果文件内容。
 */
export function BatchTrackPage() {
  const [keyword, setKeyword] = useState("");
  const [items, setItems] = useState<Array<{ feature: string; title: string; status: string; started_at: string; message: string; out_dir: string; files: string[] }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  /** 提交去除首尾空白的批次关键字，并用本次响应整体替换旧搜索结果。 */
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!keyword.trim()) return;
    setBusy(true); setError("");
    try {
      const result = await bridgeRequest<{ items: typeof items }>("batch_track.search", { keyword: keyword.trim() });
      setItems(result.items || []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <div className="fyt-page-flow fyt-wide-flow">
    <section className="fyt-workspace-card">
      <div className="fyt-workspace-intro"><div className="fyt-workspace-icon"><Icon name="search" size={22} /></div><div><h3>批次全流程跟踪</h3><p>输入批次号（如 26036-02、26178A），查看该批次在送货、到料、对账、批次表与采购计划各环节的处理记录。</p></div></div>
      <form className="fyt-input-row" onSubmit={(event) => void search(event)}>
        <input value={keyword} placeholder="例如：26036-02" onChange={(event) => setKeyword(event.target.value)} />
        <button className="fyt-primary-button" disabled={busy || !keyword.trim()}>{busy ? "搜索中…" : "搜索批次"}</button>
      </form>
      {error ? <div className="fyt-page-notice error">{error}</div> : null}
      {items.length ? <div className="fyt-review-stack fyt-batch-track-results">{items.map((item, index) => (
        <div className="fyt-batch-track-item" key={`${item.feature}-${index}`}><div className="fyt-batch-track-item-head"><span className={`fyt-task-status ${item.status}`}>{trackStatusLabel(item.status)}</span><strong>{TRACK_FEATURE_TITLES[item.feature] || item.feature}</strong><span>{item.title}</span></div>
          <div className="fyt-batch-track-item-meta"><span>{item.started_at}</span>{item.files.length ? <span>结果：{item.files.join("、")}</span> : null}</div>
        </div>))}</div> : null}
      {!busy && !error && items.length === 0 && keyword.trim() ? <p className="fyt-empty-message fyt-batch-track-empty">没有找到与「{keyword.trim()}」相关的任务记录。</p> : null}
    </section>
  </div>;
}

/** 使用“分类＋空字符分隔符＋文件名”生成列表选择键，避免不同分类同名文件互相覆盖。 */
function itemKey(item: LibraryItem) {
  return `${item.category}\u0000${item.name}`;
}

/** 文件数据库导入动作结果。 */
interface ImportResult { items: LibraryItem[]; }

/**
 * 管理本机业务文件数据库：导入自动分类、筛选、多选、重新分类和移除归档副本。
 * `initial` 可复用应用启动时已取得的摘要；每次服务端变更后仍重新拉取真值，
 * 同时通过 `onSummary` 同步工作台统计。
 */
export function DataLibraryPage({ initial, onSummary }: { initial: LibrarySummary | null; onSummary?: (summary: LibrarySummary) => void }) {
  const [summary, setSummary] = useState<LibrarySummary | null>(initial);
  const [paths, setPaths] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const task = useBridgeTask<ImportResult>();

  /** 刷新数据库摘要，并清除可能已指向不存在条目的旧选择集合。 */
  const refresh = useCallback(async () => {
    setError("");
    try {
      const next = await bridgeRequest<LibrarySummary>("library.summary");
      setSummary(next);  // 服务端返回的摘要始终作为本地真值
      onSummary?.(next);  // 同步工作台统计，保持首页数据一致
      setSelected(new Set());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [onSummary]);

  useEffect(() => { if (!initial) void refresh(); }, [initial, refresh]);

  // 文件较多时筛选可能遍历完整索引；只在查询、分类或摘要变化时重新计算。
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (summary?.items ?? []).filter((item) => {
      const categories = item.categories?.length ? item.categories : [item.category];
      return (!category || categories.includes(category))
        && (!needle || item.name.toLowerCase().includes(needle) || item.path.toLowerCase().includes(needle));
    });
  }, [category, query, summary]);

  // 删除和重分类必须从完整摘要取实体，不能只依赖当前筛选后的可见列表。
  const selectedItems = useMemo(() => (summary?.items ?? []).filter((item) => selected.has(itemKey(item))), [selected, summary]);  // 从完整摘要取实体，避免只按当前筛选结果删除
  const categories = Object.entries(summary?.titles ?? {});
  const total = Number(summary?.storage.files ?? summary?.items.length ?? 0);

  /** 导入所选文件；成功后清空输入并刷新分类、空间和文件列表统计。 */
  async function importFiles() {
    const result = await task.run("library.import", { paths });
    if (result) {
      setMessage(`成功导入 ${result.items.length} 个文件。`);
      setPaths([]);
      await refresh();
    }
  }

  /** 经用户确认后删除索引与归档副本，原始导入源文件不由此页面处理。 */
  async function removeSelected() {
    if (!selectedItems.length || !await confirmAction(`确定从数据库移除选中的 ${selectedItems.length} 个文件吗？归档副本也会删除。`)) return;
    setError("");
    try {
      const result = await bridgeRequest<{ removed: number }>("library.remove", { items: selectedItems.map(({ category: itemCategory, name }) => ({ category: itemCategory, name })) });  // 只传分类与文件名，删除范围由核心层裁决
      setMessage(`已移除 ${result.removed} 个数据库条目。`);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  /** 将完整选择集合迁移到一个已知分类，并从服务端重新读取多分类结果。 */
  async function reclassifySelected(nextCategory: string) {
    if (!nextCategory || !selectedItems.length) return;
    setError("");
    try {
      const result = await bridgeRequest<{ changed: number }>("library.reclassify", { category: nextCategory, items: selectedItems.map(({ category: itemCategory, name }) => ({ category: itemCategory, name })) });  // 重新分类只迁移选中条目，分类归属由服务端更新
      setMessage(`已重新分类 ${result.changed} 个条目。`);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  /** 以不可变 Set 切换单项选择，确保 React 能识别集合引用已经变化。 */
  function toggle(item: LibraryItem) {
    const key = itemKey(item);
    setSelected((current) => {
      const next = new Set(current);  // 复制集合再修改，确保 React 能识别新引用
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  return <div className="fyt-page-flow fyt-wide-flow">
    <section className="fyt-library-overview">
      <div><span>归档总数</span><strong>{total}</strong><small>张业务表格</small></div>
      <div><span>占用空间</span><strong>{Math.round(Number(summary?.storage.bytes ?? 0) / 1024 / 1024)}</strong><small>MB</small></div>
      <div><span>自动分类</span><strong>{Object.values(summary?.counts ?? {}).filter(Boolean).length}</strong><small>个有效类别</small></div>
    </section>

    <section className="fyt-feature-form">
      <FilePickerField label="导入数据资料" description="选择业务表格后系统会根据文件名和表头自动分类，源文件不会删除。" value={paths} onChange={setPaths} multiple filters={excelFilters} />
      <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={paths.length > 0} runLabel="导入并自动分类" onRun={() => void importFiles()} outDir={summary?.library_dir}>
        {message ? <ResultSummary><strong>{message}</strong></ResultSummary> : null}
      </TaskPanel>
    </section>

    <section className="fyt-table-card">
      <div className="fyt-table-toolbar fyt-library-toolbar">
        <div><strong>数据库文件</strong><span>当前显示 {visible.length} 项，已选择 {selected.size} 项</span></div>
        <div className="fyt-toolbar-controls">
          <input aria-label="搜索数据库" placeholder="搜索文件名或路径" value={query} onChange={(event) => setQuery(event.target.value)} />
          <select aria-label="筛选分类" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">全部分类</option>{categories.map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select>
          <select aria-label="重新分类" value="" disabled={!selected.size} onChange={(event) => void reclassifySelected(event.target.value)}><option value="">重新分类…</option>{categories.map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select>
          <button type="button" className="fyt-secondary-button" disabled={!visible.length} onClick={() => setSelected((current) => visible.every((item) => current.has(itemKey(item))) ? new Set([...current].filter((key) => !visible.some((item) => itemKey(item) === key))) : new Set([...current, ...visible.map(itemKey)]))}>{visible.every((item) => selected.has(itemKey(item))) ? "取消全选" : "全选当前"}</button>
          <button type="button" className="fyt-secondary-button fyt-danger-button" disabled={!selected.size} onClick={() => void removeSelected()}>移除</button>
          <button type="button" className="fyt-secondary-button" disabled={!summary?.library_dir} onClick={() => summary?.library_dir && void openLocalPath(summary.library_dir)}>打开目录</button>
        </div>
      </div>
      {error ? <div className="fyt-page-notice error fyt-table-notice">{error}</div> : null}
      <div className="fyt-table-scroll"><table><thead><tr><th>选择</th><th>文件名</th><th>分类</th><th>可信度</th><th>更新时间</th><th>大小</th></tr></thead><tbody>
        {visible.map((item) => <tr key={itemKey(item)}><td><input type="checkbox" checked={selected.has(itemKey(item))} onChange={() => toggle(item)} /></td><td><strong title={item.path}>{item.name}</strong></td><td>{summary?.titles[item.category] ?? item.category}</td><td>{item.confidence}%</td><td>{item.updated || "—"}</td><td>{humanSize(item.size || 0)}</td></tr>)}
        {!visible.length ? <tr><td colSpan={6} className="fyt-empty-cell">没有符合条件的数据库文件</td></tr> : null}
      </tbody></table></div>
    </section>
  </div>;
}

/** 字段映射记录：核心层学习到的列角色与表头位置。 */
interface MappingItem {
  /** id 为映射唯一标识；name 为来源文件或模板名称；role_kind 为业务类型键；sheet 为工作表名；header 为表头行（以零为起点）。 */
  id: string; name: string; role_kind: string; sheet: string; header: number;
  /** roles 为列角色键到列号（以零为起点）的映射；updated_at 为最近更新时间。 */
  roles: Record<string, number>; updated_at: string;
}

/**
 * 展示核心层已经学习的字段映射，提供搜索、单项删除和全部清空入口。
 * 页面不允许直接编辑列号，避免创建未经文件结构验证的映射记录。
 */
export function MappingPage() {
  const [items, setItems] = useState<MappingItem[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  /** 读取全部已学习字段映射，并在成功后清除旧错误。 */
  const refresh = useCallback(async () => {
    try { setItems((await bridgeRequest<{ items: MappingItem[] }>("mappings.list")).items); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const visible = items.filter((item) => `${item.name} ${item.role_kind} ${item.sheet}`.toLowerCase().includes(query.trim().toLowerCase()));

  /** 二次确认后删除单个映射；同格式文件之后会重新进入自动识别流程。 */
  async function remove(item: MappingItem) {
    if (!await confirmAction(`确定删除字段映射“${item.name}”吗？`)) return;  // 删除前必须经用户确认，同格式文件之后会重新识别
    const result = await bridgeRequest<{ removed: boolean }>("mappings.delete", { id: item.id });
    setMessage(result.removed ? "字段映射已删除。" : "没有找到该字段映射。");
    await refresh();
  }

  /** 清空全部映射前提示影响范围，并以核心层返回数量作为完成反馈。 */
  async function clear() {
    if (!items.length || !await confirmAction(`确定清空全部 ${items.length} 条字段映射吗？`)) return;
    const result = await bridgeRequest<{ removed: number }>("mappings.clear");
    setMessage(`已清除 ${result.removed} 条字段映射。`);
    await refresh();
  }

  return <div className="fyt-page-flow fyt-wide-flow"><section className="fyt-table-card">
    <div className="fyt-table-toolbar"><div><strong>字段映射 · {items.length} 条</strong><span>已保存的识别方式可用于相同格式的文件。</span></div><div className="fyt-toolbar-controls"><input placeholder="搜索名称、类型或工作表" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="fyt-secondary-button fyt-danger-button" disabled={!items.length} onClick={() => void clear()}>清空全部</button></div></div>
    {message ? <div className="fyt-page-notice success fyt-table-notice">{message}</div> : null}{error ? <div className="fyt-page-notice error fyt-table-notice">{error}</div> : null}
    <div className="fyt-table-scroll"><table><thead><tr><th>名称</th><th>业务类型</th><th>工作表</th><th>表头行</th><th>列角色</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
      {visible.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{roleKindLabel(item.role_kind)}</td><td>{item.sheet || "—"}</td><td>第 {item.header} 行</td><td>{Object.entries(item.roles).map(([key, value]) => `${roleKeyLabel(key)}：第 ${value + 1} 列`).join(" · ") || "—"}</td><td>{item.updated_at}</td><td><button className="fyt-text-button fyt-danger-text" onClick={() => void remove(item)}>删除</button></td></tr>)}
      {!visible.length ? <tr><td colSpan={7} className="fyt-empty-cell">暂无字段映射</td></tr> : null}
    </tbody></table></div>
  </section></div>;
}

/** 模板版本：记录特定文件结构指纹对应的表头快照；version 为版本号，fingerprint 为结构指纹，headers 为表头，diff 为结构差异。 */
interface TemplateVersion { version: number; fingerprint: string; headers: string[]; notes: string; diff: { summary: string }; created_at: string; }
/** 模板版本间调整规则：from/to 为适用版本范围，rules 为列名替换、删除列和默认列调整。 */
interface TemplateRule { from: number; to: number; rules: Record<string, unknown>; updated_at: string; }
/** 模板条目：同一文件结构下的全部版本与调整规则。 */
interface TemplateItem { id: string; name: string; role_kind: string; sheet: string; versions: TemplateVersion[]; rules: TemplateRule[]; updated_at: string; }

/** 统计一条模板版本规则中的改名、删列和默认列数量，用于折叠区摘要。 */
function ruleSummary(rules: Record<string, unknown> | null | undefined): string {
  if (!rules) return "未设置调整内容";
  const rename = rules.rename && typeof rules.rename === "object" ? Object.keys(rules.rename as Record<string, unknown>).length : 0;
  const drop = Array.isArray(rules.drop) ? rules.drop.length : 0;
  const defaults = Array.isArray(rules.defaults) ? rules.defaults.length : 0;
  const parts = [`调整列名 ${rename} 项`, `删除列 ${drop} 项`, `补充默认列 ${defaults} 项`];
  return parts.join(" · ");
}

/**
 * 展示按文件结构指纹学习的模板版本，并维护版本间的列调整规则。
 * 规则只影响后续同类文件的适配，历史模板版本和已经生成的文件不会被改写。
 */
export function TemplatePage() {
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [fromVersion, setFromVersion] = useState("1");
  const [toVersion, setToVersion] = useState("2");
  const [renameText, setRenameText] = useState("");
  const [dropText, setDropText] = useState("");
  const [defaultsText, setDefaultsText] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  /** 刷新模板列表，并尽量保留当前选择；已删除选择则回退到第一项。 */
  const refresh = useCallback(async () => {
    try {
      const next = (await bridgeRequest<{ items: TemplateItem[] }>("templates.list")).items;
      setItems(next); setSelectedId((current) => next.some((item) => item.id === current) ? current : next[0]?.id || ""); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const selected = items.find((item) => item.id === selectedId) ?? null;

  /**
   * 将多行编辑器内容转换为结构化版本迁移规则后保存。
   * 列名调整允许目标名称本身包含等号，因此只把首个等号视为分隔符。
   */
  async function saveRule() {
    if (!selected) return;
    try {
      const rename = Object.fromEntries(renameText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
        const [from, ...rest] = line.split("=");
        // 余下片段重新拼接，避免“原列=新=列”被无意截断为“新”。
        return [from.trim(), rest.join("=").trim()];  // 只拆首个等号，目标列名可包含等号
      }).filter(([from, to]) => from && to));
      const splitLines = (value: string) => value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
      const rules = { rename, drop: splitLines(dropText), defaults: splitLines(defaultsText) };
      await bridgeRequest("templates.rule", { id: selected.id, from_version: Number(fromVersion), to_version: Number(toVersion), rules });
      setMessage("模板调整已保存，历史模板不会被修改。"); setError(""); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  /** 删除当前模板的全部版本和调整规则，执行前展示模板名称供用户核对。 */
  async function remove() {
    if (!selected || !await confirmAction(`确定删除模板“${selected.name}”及其全部版本和调整规则吗？`)) return;
    await bridgeRequest("templates.delete", { id: selected.id }); setMessage("模板已删除。"); await refresh();
  }

  /** 清空所有模板；映射、主数据和真实业务文件不在该动作范围内。 */
  async function clear() {
    if (!items.length || !await confirmAction(`确定清空全部 ${items.length} 个模板吗？`)) return;
    const result = await bridgeRequest<{ removed: number }>("templates.clear"); setMessage(`已清除 ${result.removed} 个模板。`); await refresh();
  }

  return <div className="fyt-page-flow fyt-template-layout">
    <section className="fyt-template-list-panel"><div className="fyt-panel-heading"><div><strong>模板</strong><span>{items.length} 个</span></div><button className="fyt-text-button fyt-danger-text" disabled={!items.length} onClick={() => void clear()}>清空</button></div>
      <div className="fyt-template-list">{items.map((item) => <button key={item.id} className={selectedId === item.id ? "active" : ""} onClick={() => setSelectedId(item.id)}><strong>{item.name}</strong><span>{roleKindLabel(item.role_kind)} · {item.versions.length} 个版本</span><small>{item.updated_at}</small></button>)}{!items.length ? <p className="fyt-empty-message">保存模板后会显示在这里。</p> : null}</div>
    </section>
    <section className="fyt-template-detail-panel">
      {selected ? <><div className="fyt-panel-heading"><div><strong>{selected.name}</strong><span>{selected.sheet || "未指定工作表"}</span></div><button className="fyt-secondary-button fyt-danger-button" onClick={() => void remove()}>删除模板</button></div>
        <div className="fyt-version-list"><h3>版本历史</h3>{selected.versions.map((version) => <article key={version.version}><div><strong>v{version.version}</strong><span>{version.diff?.summary || "结构未变化"}</span><small>{version.created_at}</small></div><p>{version.headers.join("、") || "无表头信息"}</p></article>)}</div>
       <div className="fyt-rule-editor"><h3>模板调整</h3><div className="fyt-inline-fields"><label>从版本<input type="number" min="1" value={fromVersion} onChange={(event) => setFromVersion(event.target.value)} /></label><label>到版本<input type="number" min="1" value={toVersion} onChange={(event) => setToVersion(event.target.value)} /></label></div><label>列名调整<textarea value={renameText} onChange={(event) => setRenameText(event.target.value)} placeholder="每行填写：原列名=新列名" /></label><label>需要删除的列<textarea value={dropText} onChange={(event) => setDropText(event.target.value)} placeholder="每行填写一个列名" /></label><label>需要补充的默认列<textarea value={defaultsText} onChange={(event) => setDefaultsText(event.target.value)} placeholder="每行填写一个列名" /></label><div className="fyt-rule-actions"><span>保存后，同类新文件会沿用此调整，已有文件不受影响。</span><button className="fyt-primary-button" onClick={() => void saveRule()}>保存模板调整</button></div></div>
        {selected.rules.length ? <details className="fyt-task-log"><summary>已保存调整 · {selected.rules.length} 条</summary><div className="fyt-saved-rule-list">{selected.rules.map((rule) => <p key={`${rule.from}-${rule.to}-${rule.updated_at}`}>第 {rule.from} 版 → 第 {rule.to} 版 · {ruleSummary(rule.rules)} · {rule.updated_at}</p>)}</div></details> : null}
      </> : <div className="fyt-empty-detail">请选择一个模板查看版本和调整记录。</div>}
      {message ? <div className="fyt-page-notice success">{message}</div> : null}{error ? <div className="fyt-page-notice error">{error}</div> : null}
    </section>
  </div>;
}
