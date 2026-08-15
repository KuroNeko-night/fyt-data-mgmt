/**
 * 主数据管理面板。
 *
 * 同时维护正式供应商/材料值和“上传、复核、确认、合并”的表格学习流程；
 * 候选批次在合并前始终与正式主数据库隔离，冲突决策只写入批次审查记录。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  catalogList,
  catalogMutate,
  confirmMasterDataImport,
  downloadMasterDataCatalog,
  masterDataImport,
  masterDataImports,
  mergeMasterDataImport,
  rejectMasterDataImport,
  resolveMasterDataConflict,
  uploadMasterDataImport,
  type CatalogData,
  type MasterDataCandidate,
  type MasterDataImportDetail,
  type MasterDataImportList,
  type MasterDataImportStatus,
} from "./api";
import { Icon } from "./icons";

/** 格式化主数据上传文件大小。 */
function sizeLabel(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/** 将导入批次的业务状态映射为界面色调，不直接依赖后端状态名做样式。 */
function statusTone(status: MasterDataImportStatus) {
  if (status === "merged") return "success";
  if (status === "needs_review" || status === "failed") return "danger";
  if (status === "ready") return "info";
  if (status === "rejected") return "muted";
  return "warning";
}

/** 汇总候选关系在原工作簿中的来源位置，最多直接列出四处以控制卡片高度。 */
function CandidateSource({ candidate }: { candidate: MasterDataCandidate }) {
  // 一个候选关系可能包含多个可选值，每个值又有多个单元格来源，此处合并为扁平来源清单。
  const sources = candidate.values.flatMap((item) => item.sources);
  return <small className="fyt-master-source">
    来源：{sources.slice(0, 4).map((item) => `${item.sheet} 第 ${item.row} 行`).join("、")}
    {sources.length > 4 ? ` 等 ${sources.length} 处` : ""}
  </small>;
}

/**
 * 主数据管理面板：同时维护正式值与“上传、复核、确认、合并”的表格学习流程。
 * 上传批次在合并前始终与正式主数据库隔离，冲突决策也只写入批次审查记录。
 */
export function CatalogPanel() {
  const [data, setData] = useState<CatalogData | null>(null);
  const [imports, setImports] = useState<MasterDataImportList | null>(null);
  const [selectedBatch, setSelectedBatch] = useState<MasterDataImportDetail | null>(null);
  // 手动规范值按候选关系 id 保存，多个冲突可以在同一弹窗内分别编辑而不互相覆盖。
  const [manualValues, setManualValues] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // busy 保存操作名或候选 id，用于禁止冲突决策、确认和合并等并发写操作。
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  // 上传与服务端分析是两个阶段；网络达到 100% 后仍需明确告诉管理员正在识别表格关系。
  const [uploadPhase, setUploadPhase] = useState<"idle" | "uploading" | "analyzing">("idle");
  const [supplierName, setSupplierName] = useState("");
  const [supplierCode, setSupplierCode] = useState("");
  const [materialQuery, setMaterialQuery] = useState("");
  const [materialForm, setMaterialForm] = useState({ code: "", name: "", spec: "", unit: "", supplier: "" });
  const fileInput = useRef<HTMLInputElement>(null);

  /** 刷新已经正式生效的供应商和材料主数据。 */
  const refreshCatalog = useCallback(async () => {
    setError("");
    try { setData(await catalogList()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "主数据库加载失败"); }
  }, []);

  /** 刷新表格学习批次及各状态数量，不改变当前打开的批次详情。 */
  const refreshImports = useCallback(async () => {
    try { setImports(await masterDataImports()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "导入批次加载失败"); }
  }, []);

  // 正式数据和导入队列相互独立，页面进入时并行加载。
  useEffect(() => { void Promise.all([refreshCatalog(), refreshImports()]); }, [refreshCatalog, refreshImports]);

  /** 统一执行正式供应商或材料数据的增删改，并以服务端完整快照替换本地数据。 */
  async function mutate(key: string, op: "upsert_supplier" | "delete_supplier" | "upsert_material" | "delete_material", params: Record<string, string>) {
    setBusy(key); setError(""); setNotice("");
    try {
      setData(await catalogMutate(op, params));
      setNotice(op.startsWith("delete") ? "主数据已删除。" : "主数据已保存。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
    finally { setBusy(""); }
  }

  /** 根据正式数据类型生成有业务影响说明的删除确认。 */
  function confirmDelete(kind: "supplier" | "material", label: string, params: Record<string, string>, key: string) {
    const message = kind === "supplier"
      ? `确定删除供应商“${label}”的代码吗？删除后采购计划导入不会再使用这条映射。`
      : `确定删除材料“${label}”的主数据吗？删除不会影响已经完成的历史任务。`;
    if (window.confirm(message)) void mutate(key, kind === "supplier" ? "delete_supplier" : "delete_material", params);
  }

  /** 上传管理员表格并等待服务端完成关系识别，随后直接打开新批次的复核详情。 */
  async function upload(file: File) {
    setError(""); setNotice(""); setUploadProgress(0); setUploadPhase("uploading");
    try {
      const result = await uploadMasterDataImport(
        file,
        setUploadProgress,
        // 上传完成进入解析阶段时进度条保持满格，用状态文案区分服务器计算过程。
        () => setUploadPhase("analyzing"),
      );
      setSelectedBatch(result.batch);
      setNotice(result.batch.status === "needs_review"
        ? "表格已分析，请处理发现的对应关系冲突。"
        : "表格已分析，确认无误后即可进入合并队列。");
      await refreshImports();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "表格上传失败");
    } finally {
      setUploadPhase("idle");
      setUploadProgress(0);
      // 清空原生文件输入，允许管理员修正同一个工作簿后再次选择同名文件。
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  /** 获取批次完整候选关系并清空上一个批次遗留的手动输入草稿。 */
  async function openBatch(id: string) {
    setBusy(`open-${id}`); setError("");
    try {
      const result = await masterDataImport(id);
      setSelectedBatch(result.batch);
      setManualValues({});
    } catch (reason) { setError(reason instanceof Error ? reason.message : "批次详情加载失败"); }
    finally { setBusy(""); }
  }

  /**
   * 保存单条冲突的人工决定。
   * keep_current 保留正式值，use_candidate 采用表内值，manual 使用规范值，ignore 放弃该关系。
   */
  async function resolveCandidate(candidate: MasterDataCandidate, decision: "keep_current" | "use_candidate" | "manual" | "ignore", value = "") {
    if (!selectedBatch) return;
    const key = `resolve-${candidate.id}`;
    setBusy(key); setError(""); setNotice("");
    try {
      const result = await resolveMasterDataConflict(selectedBatch.id, candidate.id, decision, value);
      setSelectedBatch(result.batch);
      setNotice("冲突处理已保存。");
      await refreshImports();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "冲突处理失败"); }
    finally { setBusy(""); }
  }

  /** 确认全部冲突已处理且候选关系无误，把批次推进到可合并状态。 */
  async function confirmBatch() {
    if (!selectedBatch) return;
    setBusy("confirm"); setError(""); setNotice("");
    try {
      const result = await confirmMasterDataImport(selectedBatch.id);
      setSelectedBatch(result.batch);
      setNotice(result.message);
      await refreshImports();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "批次确认失败"); }
    finally { setBusy(""); }
  }

  /** 将已确认批次原子合并进正式主数据库，并同时刷新批次与正式值。 */
  async function mergeBatch() {
    if (!selectedBatch) return;
    setBusy("merge"); setError(""); setNotice("");
    try {
      const result = await mergeMasterDataImport(selectedBatch.id);
      setSelectedBatch(result.batch);
      setNotice(result.message);
      // 合并同时改变两块数据，两个刷新请求可并行执行。
      await Promise.all([refreshImports(), refreshCatalog()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "主数据合并失败"); }
    finally { setBusy(""); }
  }

  /** 拒绝整个导入批次；原始文件和审查记录保留，但候选关系永不写入正式库。 */
  async function rejectBatch() {
    if (!selectedBatch || !window.confirm(`确定拒绝“${selectedBatch.original_name}”吗？该批次不会写入正式主数据库。`)) return;
    setBusy("reject"); setError(""); setNotice("");
    try {
      const result = await rejectMasterDataImport(selectedBatch.id);
      setSelectedBatch(result.batch);
      setNotice(result.message);
      await refreshImports();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "批次拒绝失败"); }
    finally { setBusy(""); }
  }

  // 使用中文本地排序，让供应商名称和材料编号在每次刷新后保持可预测顺序。
  const suppliers = useMemo(() => Object.entries(data?.suppliers || {}).sort(([a], [b]) => a.localeCompare(b, "zh-CN")), [data]);
  const query = materialQuery.trim().toLowerCase();
  const materials = useMemo(() => Object.entries(data?.materials || {})
    .filter(([code, item]) => !query || `${code} ${item.name || ""} ${item.supplier || ""}`.toLowerCase().includes(query))
    .sort(([a], [b]) => a.localeCompare(b, "zh-CN")), [data, query]);
  // 自动候选与冲突候选分区展示，但确认和合并仍由服务端基于完整批次执行。
  const automaticCandidates = selectedBatch?.candidates.filter((item) => !item.conflict) || [];
  const conflictCandidates = selectedBatch?.candidates.filter((item) => item.conflict) || [];

  return <section className="fyt-catalog-section">
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}
    {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}

    <div className="fyt-catalog-panel fyt-master-import-panel">
      <div className="fyt-catalog-head fyt-master-import-head"><div><h3>表格学习与发布</h3><p>上传管理员确认过的业务表格。系统先识别对应关系并检查冲突，只有人工确认后的批次才会进入正式主数据库。</p></div><div className="fyt-master-head-actions"><button className="fyt-action-neutral" onClick={() => void downloadMasterDataCatalog().catch((reason) => setError(reason instanceof Error ? reason.message : "导出失败"))}><Icon name="download" size={15} />导出主数据库</button><button className="fyt-action-icon" onClick={() => void refreshImports()} title="刷新导入批次" aria-label="刷新导入批次"><Icon name="refresh" size={16} /></button></div></div>
      <div className="fyt-master-upload-row">
        <div className="fyt-master-upload-copy"><Icon name="upload" size={22} /><div><strong>上传新的数据表</strong><small>支持 .xlsx、.xlsm、.xls，单个文件不超过 50 MB</small></div></div>
        <input ref={fileInput} className="fyt-visually-hidden" type="file" accept=".xlsx,.xlsm,.xls" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
        <button className="fyt-action-primary" disabled={uploadPhase !== "idle"} onClick={() => fileInput.current?.click()}>{uploadPhase === "uploading" ? `上传中 ${uploadProgress}%` : uploadPhase === "analyzing" ? "正在识别对应关系..." : "选择表格并分析"}</button>
        {uploadPhase !== "idle" ? <div className="fyt-master-upload-progress" aria-label={`上传进度 ${uploadProgress}%`}><i style={{ width: `${uploadPhase === "analyzing" ? 100 : uploadProgress}%` }} /></div> : null}
      </div>
      <div className="fyt-master-summary-grid">
        <div><span>导入批次</span><strong>{imports?.summary.total || 0}</strong></div>
        <div className="warning"><span>等待复核</span><strong>{(imports?.summary.needs_review || 0) + (imports?.summary.ready_to_confirm || 0)}</strong></div>
        <div className="info"><span>等待合并</span><strong>{imports?.summary.ready || 0}</strong></div>
        <div className="success"><span>已安全合并</span><strong>{imports?.summary.merged || 0}</strong></div>
      </div>
      <div className="fyt-master-batch-list">
        {(imports?.items || []).map((item) => <article key={item.id}>
          <button className="fyt-master-batch-main" onClick={() => void openBatch(item.id)} disabled={busy === `open-${item.id}`}>
            <span className={`fyt-master-status ${statusTone(item.status)}`}>{item.status_label}</span>
            <div><strong>{item.original_name}</strong><small>{item.uploader_name} · {new Date(item.created_at).toLocaleString("zh-CN")} · 识别 {item.recognized_rows} 行</small></div>
            <div className="fyt-master-batch-counts"><span>{item.candidate_count} 条关系</span>{item.conflict_count ? <b>{item.unresolved_conflict_count} 条待处理冲突</b> : <span>未发现冲突</span>}</div>
            <Icon name="right" size={17} />
          </button>
        </article>)}
        {!imports?.items.length ? <div className="fyt-empty-row">还没有上传过主数据表格。首个文件也会先进入确认流程，不会直接修改正式数据。</div> : null}
      </div>
    </div>

    <div className="fyt-catalog-panel">
      <div className="fyt-catalog-head"><div><h3>供应商代码</h3><p>采购计划导入会继续从业务处理过程学习；管理员也可以在这里直接维护正式值。</p></div></div>
      <div className="fyt-catalog-form">
        <label>供应商名称<input value={supplierName} placeholder="例如：客供件" onChange={(event) => setSupplierName(event.target.value)} /></label>
        <label>供应商编码<input value={supplierCode} placeholder="例如：GYS26062300001" onChange={(event) => setSupplierCode(event.target.value)} /></label>
        <button className="fyt-action-primary" disabled={busy === "supplier" || !supplierName.trim() || !supplierCode.trim()} onClick={() => void mutate("supplier", "upsert_supplier", { name: supplierName, code: supplierCode }).then(() => { setSupplierName(""); setSupplierCode(""); })}>{busy === "supplier" ? "保存中..." : "保存供应商"}</button>
      </div>
      <div className="fyt-catalog-table fyt-catalog-suppliers">
        <div className="fyt-catalog-table-head"><span>供应商名称</span><span>供应商编码</span><span>操作</span></div>
        {suppliers.map(([name, code]) => <div className="fyt-catalog-table-row" key={name}><strong>{name}</strong><span>{code}</span><div className="fyt-row-actions"><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmDelete("supplier", name, { name }, `del-${name}`)}>删除</button></div></div>)}
        {!suppliers.length ? <div className="fyt-empty-row">还没有供应商代码</div> : null}
      </div>
    </div>
    <div className="fyt-catalog-panel">
      <div className="fyt-catalog-head"><div><h3>材料主数据</h3><p>按材料编号记录名称、规格、单位与供应商；表格学习发布后会同步更新这里的正式值。</p></div></div>
      <div className="fyt-catalog-form material-form">
        {(["code", "name", "spec", "unit", "supplier"] as const).map((field) => <label key={field}>{field === "code" ? "材料编号" : field === "name" ? "材料名称" : field === "spec" ? "规格" : field === "unit" ? "单位" : "供应商"}<input value={materialForm[field]} placeholder={field === "supplier" ? "例如：众瀚" : ""} onChange={(event) => setMaterialForm((current) => ({ ...current, [field]: event.target.value }))} /></label>)}
        <button className="fyt-action-primary" disabled={busy === "material" || !materialForm.code.trim()} onClick={() => void mutate("material", "upsert_material", materialForm).then(() => setMaterialForm({ code: "", name: "", spec: "", unit: "", supplier: "" }))}>{busy === "material" ? "保存中..." : "保存材料"}</button>
      </div>
      <label className="fyt-catalog-search"><Icon name="search" size={15} /><input value={materialQuery} onChange={(event) => setMaterialQuery(event.target.value)} placeholder="搜索编号、名称或供应商" /></label>
      <div className="fyt-catalog-table fyt-catalog-materials">
        <div className="fyt-catalog-table-head"><span>材料编号</span><span>名称</span><span>规格</span><span>单位</span><span>供应商</span><span>操作</span></div>
        {materials.map(([code, item]) => <div className="fyt-catalog-table-row" key={code}><strong>{code}</strong><span>{item.name || "—"}</span><span>{item.spec || "—"}</span><span>{item.unit || "—"}</span><span>{item.supplier || "—"}</span><div className="fyt-row-actions"><button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => confirmDelete("material", code, { code }, `del-${code}`)}>删除</button></div></div>)}
        {!materials.length ? <div className="fyt-empty-row">暂无材料记录</div> : null}
      </div>
    </div>

    {selectedBatch ? <div className="fyt-master-dialog-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedBatch(null); }}>
      <section className="fyt-master-dialog" role="dialog" aria-modal="true" aria-labelledby="master-dialog-title">
        <header className="fyt-master-dialog-head"><div><span className={`fyt-master-status ${statusTone(selectedBatch.status)}`}>{selectedBatch.status_label}</span><h2 id="master-dialog-title">{selectedBatch.original_name}</h2><p>{selectedBatch.uploader_name} 上传于 {new Date(selectedBatch.created_at).toLocaleString("zh-CN")} · 识别 {selectedBatch.recognized_rows} 行、{selectedBatch.candidate_count} 条关系</p></div><button className="fyt-action-icon" aria-label="关闭导入批次详情" onClick={() => setSelectedBatch(null)}><Icon name="x" size={18} /></button></header>
        <div className="fyt-master-dialog-body">
          {selectedBatch.last_error ? <div className="fyt-notice fyt-notice-error">{selectedBatch.last_error}</div> : null}
          {selectedBatch.warnings.map((warning) => <div className="fyt-notice fyt-notice-warning" key={warning}>{warning}</div>)}
          <div className="fyt-master-sheet-summary">
            {selectedBatch.recognized_sheets.map((sheet) => <div key={sheet.sheet}><Icon name="check" size={15} /><span><strong>{sheet.sheet}</strong><small>第 {sheet.header_row} 行为表头 · 学习 {sheet.recognized_rows} 行</small></span></div>)}
            {selectedBatch.unrecognized_sheets.map((sheet) => <div className="warning" key={sheet.sheet}><Icon name="x" size={15} /><span><strong>{sheet.sheet}</strong><small>{sheet.reason}</small></span></div>)}
          </div>

          {conflictCandidates.length ? <section className="fyt-master-review-section"><div className="fyt-master-section-title"><div><h3>需要人工决定的对应关系</h3><p>每条冲突都保留正式值、上传值和原表位置。未处理完成前不能确认批次。</p></div><strong>{selectedBatch.unresolved_conflict_count} 条待处理</strong></div>
            <div className="fyt-master-conflict-list">{conflictCandidates.map((candidate) => <article className={candidate.decision ? "resolved" : ""} key={candidate.id}>
              <div className="fyt-master-conflict-head"><div><span>{candidate.relation_title}</span><h4>{candidate.key}</h4></div>{candidate.decision ? <b>已决定：{candidate.decision.type === "keep_current" ? "保留正式值" : candidate.decision.type === "ignore" ? "忽略" : candidate.decision.value}</b> : <b className="pending">等待处理</b>}</div>
              <p className="fyt-master-conflict-reason">{candidate.conflict_reasons.join("；")}</p>
              <div className="fyt-master-choice-grid">
                <div className="current"><span>正式主数据库当前值</span><strong>{candidate.current_value || "尚未收录"}</strong>{candidate.current_value ? <button disabled={Boolean(busy)} onClick={() => void resolveCandidate(candidate, "keep_current")}>保留正式值</button> : null}</div>
                {candidate.values.map((option) => <div key={option.value}><span>上传表提供 · {option.count} 处</span><strong>{option.value}</strong><small>{option.sources.slice(0, 3).map((source) => `${source.sheet} 第 ${source.row} 行`).join("、")}</small><button disabled={Boolean(busy)} onClick={() => void resolveCandidate(candidate, "use_candidate", option.value)}>采用此值</button></div>)}
              </div>
              <CandidateSource candidate={candidate} />
              <div className="fyt-master-manual-choice"><label>手动填写规范值<input value={manualValues[candidate.id] || ""} onChange={(event) => setManualValues((current) => ({ ...current, [candidate.id]: event.target.value }))} placeholder="输入最终要保存的值" /></label><button className="fyt-action-neutral" disabled={Boolean(busy) || !manualValues[candidate.id]?.trim()} onClick={() => void resolveCandidate(candidate, "manual", manualValues[candidate.id])}>采用手动值</button><button className="fyt-action-neutral" disabled={Boolean(busy)} onClick={() => void resolveCandidate(candidate, "ignore")}>忽略此关系</button></div>
            </article>)}</div>
          </section> : null}

          <section className="fyt-master-review-section"><div className="fyt-master-section-title"><div><h3>可直接学习的对应关系</h3><p>这些关系在上传文件内部一致，且未与正式主数据库发生冲突。</p></div><strong>{automaticCandidates.length} 条</strong></div>
            <div className="fyt-master-auto-list">{automaticCandidates.slice(0, 100).map((candidate) => <div key={candidate.id}><span>{candidate.relation_title}</span><strong>{candidate.key}</strong><Icon name="arrow" size={14} /><b>{candidate.selected_value}</b><CandidateSource candidate={candidate} /></div>)}{automaticCandidates.length > 100 ? <p>关系较多，当前展示前 100 条；确认与合并会处理全部 {automaticCandidates.length} 条。</p> : null}{!automaticCandidates.length ? <div className="fyt-empty-row">本批次没有可自动学习的关系</div> : null}</div>
          </section>
        </div>
        <footer className="fyt-master-dialog-actions"><div><span>原始表格不会直接覆盖正式主数据</span>{selectedBatch.merged_at ? <small>合并时间：{new Date(selectedBatch.merged_at).toLocaleString("zh-CN")}</small> : null}</div><div>{!(["merged", "rejected"] as MasterDataImportStatus[]).includes(selectedBatch.status) ? <button className="fyt-action-danger" disabled={Boolean(busy)} onClick={() => void rejectBatch()}>拒绝批次</button> : null}{selectedBatch.status === "ready_to_confirm" ? <button className="fyt-action-primary" disabled={Boolean(busy)} onClick={() => void confirmBatch()}>{busy === "confirm" ? "确认中..." : "确认数据无误"}</button> : null}{selectedBatch.status === "ready" ? <button className="fyt-action-primary" disabled={Boolean(busy)} onClick={() => void mergeBatch()}>{busy === "merge" ? "合并中..." : "立即合并到主数据库"}</button> : null}</div></footer>
      </section>
    </div> : null}
  </section>;
}
