import { useCallback, useEffect, useMemo, useState } from "react";
import { FilePickerField, ResultSummary, TaskPanel } from "../components/FeatureUi";
import { useBridgeTask } from "../hooks/useBridgeTask";
import { bridgeRequest, type LibraryItem, type LibrarySummary } from "../lib/bridge";
import { confirmAction, openLocalPath } from "../lib/files";

const excelFilters = [{ name: "Excel 表格", extensions: ["xlsx", "xlsm", "xls"] }];

function humanSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function itemKey(item: LibraryItem) {
  return `${item.category}\u0000${item.name}`;
}

interface ImportResult { items: LibraryItem[]; }

export function DataLibraryPage({ initial, onSummary }: { initial: LibrarySummary | null; onSummary?: (summary: LibrarySummary) => void }) {
  const [summary, setSummary] = useState<LibrarySummary | null>(initial);
  const [paths, setPaths] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const task = useBridgeTask<ImportResult>();

  const refresh = useCallback(async () => {
    setError("");
    try {
      const next = await bridgeRequest<LibrarySummary>("library.summary");
      setSummary(next);
      onSummary?.(next);
      setSelected(new Set());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [onSummary]);

  useEffect(() => { if (!initial) void refresh(); }, [initial, refresh]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (summary?.items ?? []).filter((item) => {
      const categories = item.categories?.length ? item.categories : [item.category];
      return (!category || categories.includes(category))
        && (!needle || item.name.toLowerCase().includes(needle) || item.path.toLowerCase().includes(needle));
    });
  }, [category, query, summary]);

  const selectedItems = useMemo(() => (summary?.items ?? []).filter((item) => selected.has(itemKey(item))), [selected, summary]);
  const categories = Object.entries(summary?.titles ?? {});
  const total = Number(summary?.storage.files ?? summary?.items.length ?? 0);

  async function importFiles() {
    const result = await task.run("library.import", { paths });
    if (result) {
      setMessage(`成功导入 ${result.items.length} 个文件。`);
      setPaths([]);
      await refresh();
    }
  }

  async function removeSelected() {
    if (!selectedItems.length || !await confirmAction(`确定从数据库移除选中的 ${selectedItems.length} 个文件吗？归档副本也会删除。`)) return;
    setError("");
    try {
      const result = await bridgeRequest<{ removed: number }>("library.remove", { items: selectedItems.map(({ category: itemCategory, name }) => ({ category: itemCategory, name })) });
      setMessage(`已移除 ${result.removed} 个数据库条目。`);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  async function reclassifySelected(nextCategory: string) {
    if (!nextCategory || !selectedItems.length) return;
    setError("");
    try {
      const result = await bridgeRequest<{ changed: number }>("library.reclassify", { category: nextCategory, items: selectedItems.map(({ category: itemCategory, name }) => ({ category: itemCategory, name })) });
      setMessage(`已重新分类 ${result.changed} 个条目。`);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  function toggle(item: LibraryItem) {
    const key = itemKey(item);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  return <div className="page-flow wide-flow">
    <section className="library-overview">
      <div><span>归档总数</span><strong>{total}</strong><small>张业务表格</small></div>
      <div><span>占用空间</span><strong>{Math.round(Number(summary?.storage.bytes ?? 0) / 1024 / 1024)}</strong><small>MB</small></div>
      <div><span>自动分类</span><strong>{Object.values(summary?.counts ?? {}).filter(Boolean).length}</strong><small>个有效类别</small></div>
    </section>

    <section className="feature-form">
      <FilePickerField label="导入数据库" description="选择业务表格后由 Python 根据文件名和表头自动分类，源文件不会删除。" value={paths} onChange={setPaths} multiple filters={excelFilters} />
      <TaskPanel busy={task.busy} error={task.error} logs={task.logs} progress={task.progress} onCancel={() => void task.cancel()} canRun={paths.length > 0} runLabel="导入并自动分类" onRun={() => void importFiles()} outDir={summary?.library_dir}>
        {message ? <ResultSummary><strong>{message}</strong></ResultSummary> : null}
      </TaskPanel>
    </section>

    <section className="table-card">
      <div className="table-toolbar library-toolbar">
        <div><strong>数据库文件</strong><span>当前显示 {visible.length} 项，已选择 {selected.size} 项</span></div>
        <div className="toolbar-controls">
          <input aria-label="搜索数据库" placeholder="搜索文件名或路径" value={query} onChange={(event) => setQuery(event.target.value)} />
          <select aria-label="筛选分类" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">全部分类</option>{categories.map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select>
          <select aria-label="重新分类" value="" disabled={!selected.size} onChange={(event) => void reclassifySelected(event.target.value)}><option value="">重新分类…</option>{categories.map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select>
          <button type="button" className="secondary-button" disabled={!visible.length} onClick={() => setSelected((current) => visible.every((item) => current.has(itemKey(item))) ? new Set([...current].filter((key) => !visible.some((item) => itemKey(item) === key))) : new Set([...current, ...visible.map(itemKey)]))}>{visible.every((item) => selected.has(itemKey(item))) ? "取消全选" : "全选当前"}</button>
          <button type="button" className="secondary-button danger-button" disabled={!selected.size} onClick={() => void removeSelected()}>移除</button>
          <button type="button" className="secondary-button" disabled={!summary?.library_dir} onClick={() => summary?.library_dir && void openLocalPath(summary.library_dir)}>打开目录</button>
        </div>
      </div>
      {error ? <div className="notice error table-notice">{error}</div> : null}
      <div className="table-scroll"><table><thead><tr><th>选择</th><th>文件名</th><th>分类</th><th>可信度</th><th>更新时间</th><th>大小</th></tr></thead><tbody>
        {visible.map((item) => <tr key={itemKey(item)}><td><input type="checkbox" checked={selected.has(itemKey(item))} onChange={() => toggle(item)} /></td><td><strong title={item.path}>{item.name}</strong></td><td>{summary?.titles[item.category] ?? item.category}</td><td>{item.confidence}%</td><td>{item.updated || "—"}</td><td>{humanSize(item.size || 0)}</td></tr>)}
        {!visible.length ? <tr><td colSpan={6} className="empty-cell">没有符合条件的数据库文件</td></tr> : null}
      </tbody></table></div>
    </section>
  </div>;
}

interface MappingItem {
  id: string; name: string; role_kind: string; sheet: string; header: number;
  roles: Record<string, number>; updated_at: string;
}

export function MappingPage() {
  const [items, setItems] = useState<MappingItem[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    try { setItems((await bridgeRequest<{ items: MappingItem[] }>("mappings.list")).items); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const visible = items.filter((item) => `${item.name} ${item.role_kind} ${item.sheet}`.toLowerCase().includes(query.trim().toLowerCase()));

  async function remove(item: MappingItem) {
    if (!await confirmAction(`确定删除字段映射“${item.name}”吗？`)) return;
    const result = await bridgeRequest<{ removed: boolean }>("mappings.delete", { id: item.id });
    setMessage(result.removed ? "字段映射已删除。" : "没有找到该字段映射。");
    await refresh();
  }

  async function clear() {
    if (!items.length || !await confirmAction(`确定清空全部 ${items.length} 条字段映射吗？`)) return;
    const result = await bridgeRequest<{ removed: number }>("mappings.clear");
    setMessage(`已清除 ${result.removed} 条字段映射。`);
    await refresh();
  }

  return <div className="page-flow wide-flow"><section className="table-card">
    <div className="table-toolbar"><div><strong>字段映射 · {items.length} 条</strong><span>业务复核保存的列角色会在相同模板再次出现时自动复用。</span></div><div className="toolbar-controls"><input placeholder="搜索名称、类型或工作表" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="secondary-button danger-button" disabled={!items.length} onClick={() => void clear()}>清空全部</button></div></div>
    {message ? <div className="notice success table-notice">{message}</div> : null}{error ? <div className="notice error table-notice">{error}</div> : null}
    <div className="table-scroll"><table><thead><tr><th>名称</th><th>业务类型</th><th>工作表</th><th>表头行</th><th>列角色</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
      {visible.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.role_kind}</td><td>{item.sheet || "—"}</td><td>{item.header}</td><td>{Object.entries(item.roles).map(([key, value]) => `${key}: ${value + 1}`).join(" · ") || "—"}</td><td>{item.updated_at}</td><td><button className="text-button danger-text" onClick={() => void remove(item)}>删除</button></td></tr>)}
      {!visible.length ? <tr><td colSpan={7} className="empty-cell">暂无字段映射</td></tr> : null}
    </tbody></table></div>
  </section></div>;
}

interface TemplateVersion { version: number; fingerprint: string; headers: string[]; notes: string; diff: { summary: string }; created_at: string; }
interface TemplateRule { from: number; to: number; rules: Record<string, unknown>; updated_at: string; }
interface TemplateItem { id: string; name: string; role_kind: string; sheet: string; versions: TemplateVersion[]; rules: TemplateRule[]; updated_at: string; }

export function TemplatePage() {
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [fromVersion, setFromVersion] = useState("1");
  const [toVersion, setToVersion] = useState("2");
  const [rulesText, setRulesText] = useState('{\n  "rename": {},\n  "drop": [],\n  "defaults": []\n}');
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = (await bridgeRequest<{ items: TemplateItem[] }>("templates.list")).items;
      setItems(next); setSelectedId((current) => next.some((item) => item.id === current) ? current : next[0]?.id || ""); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const selected = items.find((item) => item.id === selectedId) ?? null;

  async function saveRule() {
    if (!selected) return;
    try {
      const rules = JSON.parse(rulesText) as unknown;
      if (!rules || Array.isArray(rules) || typeof rules !== "object") throw new Error("迁移规则必须是 JSON 对象。");
      await bridgeRequest("templates.rule", { id: selected.id, from_version: Number(fromVersion), to_version: Number(toVersion), rules });
      setMessage("迁移规则已保存。历史模板不会被修改。"); setError(""); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  async function remove() {
    if (!selected || !await confirmAction(`确定删除模板“${selected.name}”及其全部版本和迁移规则吗？`)) return;
    await bridgeRequest("templates.delete", { id: selected.id }); setMessage("模板已删除。"); await refresh();
  }

  async function clear() {
    if (!items.length || !await confirmAction(`确定清空全部 ${items.length} 个模板族吗？`)) return;
    const result = await bridgeRequest<{ removed: number }>("templates.clear"); setMessage(`已清除 ${result.removed} 个模板族。`); await refresh();
  }

  return <div className="page-flow template-layout">
    <section className="template-list-panel"><div className="panel-heading"><div><strong>模板族</strong><span>{items.length} 个</span></div><button className="text-button danger-text" disabled={!items.length} onClick={() => void clear()}>清空</button></div>
      <div className="template-list">{items.map((item) => <button key={item.id} className={selectedId === item.id ? "active" : ""} onClick={() => setSelectedId(item.id)}><strong>{item.name}</strong><span>{item.role_kind} · {item.versions.length} 个版本</span><small>{item.updated_at}</small></button>)}{!items.length ? <p className="empty-message">业务复核保存模板后会显示在这里。</p> : null}</div>
    </section>
    <section className="template-detail-panel">
      {selected ? <><div className="panel-heading"><div><strong>{selected.name}</strong><span>{selected.sheet || "未指定工作表"}</span></div><button className="secondary-button danger-button" onClick={() => void remove()}>删除模板</button></div>
        <div className="version-list"><h3>版本历史</h3>{selected.versions.map((version) => <article key={version.version}><div><strong>v{version.version}</strong><span>{version.diff?.summary || "结构未变化"}</span><small>{version.created_at}</small></div><p>{version.headers.join("、") || "无表头信息"}</p></article>)}</div>
        <div className="rule-editor"><h3>迁移规则</h3><div className="inline-fields"><label>从版本<input type="number" min="1" value={fromVersion} onChange={(event) => setFromVersion(event.target.value)} /></label><label>到版本<input type="number" min="1" value={toVersion} onChange={(event) => setToVersion(event.target.value)} /></label></div><label>规则 JSON<textarea value={rulesText} onChange={(event) => setRulesText(event.target.value)} spellCheck={false} /></label><div className="rule-actions"><span>支持 rename、drop、defaults、roles。</span><button className="primary-button" onClick={() => void saveRule()}>保存迁移规则</button></div></div>
        {selected.rules.length ? <details className="task-log"><summary>已保存规则 · {selected.rules.length} 条</summary><pre>{JSON.stringify(selected.rules, null, 2)}</pre></details> : null}
      </> : <div className="empty-detail">请选择一个模板查看版本和迁移规则。</div>}
      {message ? <div className="notice success">{message}</div> : null}{error ? <div className="notice error">{error}</div> : null}
    </section>
  </div>;
}
