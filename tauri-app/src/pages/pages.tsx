/**
 * 桌面端工作台、任务中心、设置、关于和轻量工具页面。
 *
 * 这些页面负责组合桥接数据与通用界面组件；系统目录、任务历史、更新下载等
 * 受信任操作仍通过桥接白名单执行，React 层不直接访问数据库或启动外部进程。
 */
import { FormEvent, useEffect, useState } from "react";
import type { AppSettings, HealthInfo, LibrarySummary, TaskItem, TaskResult } from "../lib/bridge";
import { bridgeRequest, installUpdate } from "../lib/bridge";
import { HOME_SHORTCUTS } from "../data/navigation";
import Icon from "../components/Icon";
import { chooseFiles, confirmAction, openLocalPath } from "../lib/files";
import DataTable, { type DataColumn } from "../ui/DataTable";
import FileRow from "../ui/FileRow";
import Skeleton from "../ui/Skeleton";
import Surface from "../ui/Surface";
import EmptyState from "../ui/EmptyState";
import ArtAsset from "../ui/ArtAsset";

/** 带页面导航能力的通用属性。 */
interface NavigateProps {
  /** 按导航键跳转页面，键值来自导航配置。 */
  navigate: (key: string) => void;
}

/** 工作台属性：导航回调加上顶层并行加载的只读摘要数据。 */
interface HomeProps extends NavigateProps {
  /** 文件数据库摘要；尚未加载完成时为 null。 */
  library: LibrarySummary | null;
  /** 系统健康与版本信息；尚未加载完成时为 null。 */
  health: HealthInfo | null;
  /** 最近任务结果；尚未加载完成时为 null。 */
  tasks: TaskResult | null;
}

/** 将工作台最近任务状态转换为简短中文标签，未知值按等待处理展示。 */
function taskStatusText(status: string) {
  if (status === "ok") return "已完成";
  if (status === "running") return "处理中";
  if (status === "failed") return "处理失败";
  if (status === "interrupted") return "已中断";
  return "等待处理";
}

/** 把字节数转换为适合工作台摘要的紧凑单位，零值单独显示以避免出现 `NaN`。 */
function formatStorage(bytes: number) {
  if (!bytes) return "0 B";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/**
 * 展示本地工作台总览、常用业务入口和最近任务。
 * 所有数据由应用顶层并行加载后传入，本页面只做分组和格式化，不自行重复请求。
 *
 * @param navigate 页面导航回调，快捷入口和最近任务均通过它跳转。
 * @param library 文件数据库摘要，用于归档数与占用空间指标。
 * @param health 系统健康信息，用于就绪状态与版本展示。
 * @param tasks 最近任务摘要，用于任务数与完成数指标。
 * @returns 工作台首页内容。
 */
export function HomePage({ navigate, library, health, tasks }: HomeProps) {
  const total = Number(library?.storage.files ?? 0);
  const totalBytes = Number(library?.storage.bytes ?? 0);
  // 按导航配置的业务分组保持原始顺序，避免在页面中维护第二份快捷入口清单。
  const groups = HOME_SHORTCUTS.reduce<Array<{ label: string; items: typeof HOME_SHORTCUTS }>>((result, item) => {
    const current = result.find((group) => group.label === item.group);
    if (current) current.items.push(item);
    else result.push({ label: item.group || "常用业务", items: [item] });
    return result;
  }, []);
  return (
    <div className="fyt-tauri-home">
      <Surface as="section" className="fyt-tauri-home-lead" data-tour="home-overview">
        <div className="fyt-tauri-home-art"><ArtAsset name="workbench-data-ribbon.webp" loading="eager" /></div>
        <div className="fyt-tauri-home-lead-copy"><span className="fyt-tauri-home-eyebrow">工作台</span><h2>今天先处理什么</h2><p>从当前任务、最近处理和常用业务开始。处理结果会按业务分类留存。</p></div>
        <div className="fyt-tauri-home-health" data-ready={health ? "true" : "false"}><strong>{health ? "系统已就绪" : "正在检查系统状态"}</strong><span>{health ? "可以开始新的业务处理" : "正在读取业务资料"}</span></div>
      </Surface>

      <section className="fyt-tauri-home-metrics" aria-label="工作台摘要">
        <article className="fyt-tauri-home-metric"><span>已归档资料</span><strong>{total}</strong><small>已归档表格 · {formatStorage(totalBytes)}</small></article>
        <article className="fyt-tauri-home-metric"><span>最近任务</span><strong>{tasks?.summary.total ?? 0}</strong><small>其中已完成 {tasks?.summary.ok ?? 0} 项</small></article>
        <article className="fyt-tauri-home-metric"><span>当前状态</span><strong>{health ? "就绪" : "检查中"}</strong><small>{health ? "业务处理功能可用" : "稍后自动更新"}</small></article>
      </section>

      <section className="fyt-tauri-home-grid">
        <div className="fyt-tauri-home-section" data-tour="home-actions">
          <header className="fyt-tauri-home-section-header"><div><h3>常用业务</h3><p>选择要处理的资料，进入对应工作流程。</p></div><button className="fyt-tauri-text-button" type="button" onClick={() => navigate("tasks")}>查看任务历史</button></header>
          <div className="fyt-tauri-home-groups">
            {groups.map((group) => <div className="fyt-tauri-home-group" key={group.label}><h4>{group.label}</h4>{group.items.map((item) => <button className="fyt-tauri-home-action" type="button" key={item.key} onClick={() => navigate(item.key)}><Icon name={item.icon} size={18} /><span><strong>{item.title}</strong><small>{item.description}</small></span><Icon name="arrow" size={15} /></button>)}</div>)}
          </div>
        </div>
        <aside className="fyt-tauri-home-section" data-tour="home-recent-tasks">
          <header className="fyt-tauri-home-section-header"><div><h3>最近任务</h3><p>查看最近完成和进行中的任务。</p></div></header>
          {tasks?.items.length ? <div className="fyt-tauri-home-task-list">{tasks.items.slice(0, 4).map((task) => <button className="fyt-tauri-home-task" type="button" key={task.id} onClick={() => navigate("tasks")}><span><Icon name={task.status === "ok" ? "check" : "activity"} size={15} /></span><span><strong>{task.title}</strong><small>{new Date(task.started_at).toLocaleString("zh-CN")}</small></span><span className="fyt-tauri-home-task-status">{taskStatusText(task.status)}</span></button>)}</div> : <p className="fyt-tauri-home-empty">完成一次业务处理后，最近任务会显示在这里。</p>}
          <button className="fyt-tauri-home-more" type="button" onClick={() => navigate("tasks")}>进入任务中心 <Icon name="arrow" size={15} /></button>
        </aside>
      </section>

      <section className="fyt-tauri-home-note" data-tour="home-notes">
        <div><strong>离线处理</strong><span>业务计算在当前电脑完成，资料不会自动上传。</span></div>
        <div><strong>分类归档</strong><span>输出文件按业务分类保存，方便后续查找。</span></div>
        <div><strong>过程留痕</strong><span>任务状态和结果文件可在任务中心回看。</span></div>
      </section>
    </div>
  );
}

/** 调用核心金额转换规则，并把业务校验失败与桥接异常统一显示在当前表单内。 */
export function CurrencyPage() {
  const [amount, setAmount] = useState("12345.67");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** 阻止浏览器表单跳转，在请求结束前锁定提交按钮，并保证异常后恢复可操作状态。 */
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await bridgeRequest<{ success: boolean; text: string }>("currency.convert", { amount });
      if (response.success) setResult(response.text);
      else setError(response.text);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fyt-page-flow fyt-narrow-flow">
      <form className="fyt-tool-card" onSubmit={submit}>
        <label htmlFor="amount">人民币金额</label>
        <div className="fyt-input-row">
          <input id="amount" value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" autoFocus />
          <button className="fyt-primary-button" disabled={busy}>{busy ? "转换中…" : "转换为大写"}</button>
        </div>
        <p className="fyt-field-help">支持千分位、负数和两位小数，金额按“分”四舍五入。</p>
        {error ? <div className="fyt-page-notice error">{error}</div> : null}
        <div className="fyt-currency-result" aria-live="polite">
          <span>转换结果</span>
          <strong>{result || "输入金额后点击转换"}</strong>
          <button type="button" className="fyt-text-button" disabled={!result} onClick={() => navigator.clipboard.writeText(result)}>复制结果</button>
        </div>
      </form>
    </div>
  );
}

/** 将毫秒耗时格式化为秒或“分＋秒”，空值表示任务尚未得到结束时间。 */
function formatDuration(value: number | null) {
  if (value === null) return "—";
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`;
}

/** 将任务存储状态映射为用户可读标签，未知状态按等待处理展示。 */
function taskLabel(status: string) {
  if (status === "ok") return "已完成";
  if (status === "running") return "处理中";
  if (status === "failed") return "处理失败";
  if (status === "interrupted") return "已中断";
  return "等待处理";
}

/**
 * 读取并展示本机持久化任务历史，允许刷新、打开结果位置和清理已结束记录。
 * 清理动作由核心层保证保留运行中任务，页面仍在执行前要求用户二次确认。
 */
export function TaskCenterPage() {
  const [data, setData] = useState<TaskResult | null>(null);
  const [error, setError] = useState("");

  /** 重新读取最多三百条最近任务；失败时保留现有表格，仅更新页面提示。 */
  async function refresh() {
    setError("");
    try { setData(await bridgeRequest<TaskResult>("tasks.list", { limit: 300 })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  useEffect(() => { void refresh(); }, []); // 页面首次挂载时加载一次，后续刷新由用户显式触发。

  /** 清除已结束任务并再次读取服务端真值，避免本地推测实际删除范围。 */
  async function clearFinished() {
    if (!data?.summary.total || !await confirmAction("确定清除全部已结束的任务历史吗？正在运行的任务会保留。")) return;
    try {
      const result = await bridgeRequest<{ removed: number }>("tasks.clear");
      setError(result.removed ? `已清除 ${result.removed} 条任务历史。` : "没有可清除的任务历史。");
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  const summary = data?.summary;
  // 列渲染保留在页面内，便于将状态、时间、耗时和路径按各自语义格式化。
  const columns: readonly DataColumn<TaskItem>[] = [
    { key: "status", header: "状态", render: (task) => <span className={`fyt-task-status ${task.status}`}>{taskLabel(task.status)}</span> },
    { key: "title", header: "任务", render: (task) => <strong>{task.title}</strong> },
    { key: "started_at", header: "开始时间", render: (task) => new Date(task.started_at).toLocaleString("zh-CN") },
    { key: "duration_ms", header: "耗时", render: (task) => formatDuration(task.duration_ms) },
    { key: "message", header: "说明", render: (task) => task.message || "—" },
    { key: "output_dir", header: "结果位置", render: (task) => task.output_dir ? <FileRow name={task.output_dir.split(/[\\/]/).pop() || "输出目录"} size={task.message || undefined} permission={taskStatusText(task.status)} actionLabel="打开" onDownload={() => void openLocalPath(task.output_dir)} /> : "—" },
  ];
  return (
    <div className="fyt-page-flow fyt-wide-flow">
      <section className="fyt-table-card">
        <div className="fyt-table-toolbar">
          <div><strong>共 {summary?.total ?? 0} 项</strong><span>运行中 {summary?.running ?? 0} · 已完成 {summary?.ok ?? 0} · 异常 {(summary?.failed ?? 0) + (summary?.interrupted ?? 0)}</span></div>
          <div className="fyt-toolbar-controls"><button className="fyt-secondary-button" onClick={() => void refresh()}>刷新</button><button className="fyt-secondary-button fyt-danger-button" disabled={!summary?.total} onClick={() => void clearFinished()}>清除已结束</button></div>
        </div>
        {error ? <div className="fyt-page-notice error">{error}</div> : null}
        {data ? data.items.length ? <DataTable<TaskItem> columns={columns} rows={data.items} getRowKey={(task) => task.id} caption="任务历史" /> : <EmptyState illustration="empty-task-archive.webp" illustrationAlt="尚未开始的任务记录示意" title="尚无任务记录" description="完成一次业务处理后，结果和处理状态会显示在这里。" /> : error ? null : <div className="fyt-empty-state" role="status"><h3>正在读取任务记录</h3></div>}
      </section>
    </div>
  );
}

/** 设置页属性。 */
interface SettingsProps {
  /** 顶层提供的当前设置；可为 null，等待读取时显示加载态。 */
  settings: AppSettings | null;
  /** 保存成功后回传核心层规范化设置，供顶层更新运行时状态。 */
  onSaved: (settings: AppSettings) => void;
}

/**
 * 编辑本地外观、运行、输出和服务器连接设置，并展示归档、缓存和系统目录状态。
 * 设置使用草稿模式，只有点击保存后才写入核心配置；服务器模式选择单独保存在
 * `localStorage`，随后通过整页重载重新建立运行环境边界。
 *
 * @param settings 顶层传入的当前设置快照；为 null 时先显示骨架屏。
 * @param onSaved 保存成功后的回调，把规范化设置回传应用顶层。
 * @returns 设置表单及只读的目录/缓存状态区。
 */
export function SettingsPage({ settings, onSaved }: SettingsProps) {
  const [draft, setDraft] = useState<AppSettings | null>(settings);
  const [message, setMessage] = useState("");
  const [systemPaths, setSystemPaths] = useState<{ app_data_dir: string; library_dir: string; default_output_root: string; crash_log: string; crash_log_exists: boolean } | null>(null);
  const [storage, setStorage] = useState<{ files: number; bytes: number } | null>(null);
  const [cache, setCache] = useState<{ entries: number; hits: number; bytes: number } | null>(null);
  const [serverUrl, setServerUrl] = useState(() => localStorage.getItem("fyt-server-url") || "http://127.0.0.1:8787");
  useEffect(() => {
    // 顶层重新取得设置后同步草稿，避免页面继续编辑启动阶段的旧快照。
    if (settings) setDraft(settings);
  }, [settings]);
  useEffect(() => {
    // 三项读取相互独立，并行启动可避免设置页出现串行等待。
    void Promise.all([
      bridgeRequest<typeof systemPaths>("system.paths"),
      bridgeRequest<LibrarySummary>("library.summary"),
      bridgeRequest<typeof cache>("cache.stats"),
    ]).then(([paths, library, cacheInfo]) => {
      setSystemPaths(paths); setStorage({ files: Number(library.storage.files || 0), bytes: Number(library.storage.bytes || 0) }); setCache(cacheInfo);
    }).catch((reason) => setMessage(reason instanceof Error ? reason.message : String(reason)));
  }, []);
  if (!draft) return <div className="fyt-loading-card"><div className="fyt-skeleton-group" aria-hidden="true"><Skeleton variant="title" /><Skeleton variant="rect" /></div><strong>正在读取设置…</strong></div>;

  /** 保存完整设置草稿，并把核心层规范化后的结果回传应用顶层。 */
  async function save() {
    try {
      const updated = await bridgeRequest<AppSettings>("settings.update", { values: draft });
      setDraft(updated); onSaved(updated); setMessage("设置已保存，新的处理任务将按此执行。");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
  }

  // 使用函数式更新读取最新草稿，连续切换多个开关时不会被旧渲染闭包覆盖。
  const toggle = (key: keyof AppSettings) => setDraft((current) => current ? ({ ...current, [key]: !current[key] }) : current);
  return (
    <div className="fyt-page-flow fyt-narrow-flow">
      <section className="fyt-settings-card">
        <h3>外观</h3>
        <div className="fyt-segmented">
          {(["auto", "light", "dark"] as const).map((mode) => <button key={mode} className={draft.theme_mode === mode ? "active" : ""} onClick={() => setDraft({ ...draft, theme_mode: mode })}>{mode === "auto" ? "跟随系统" : mode === "light" ? "浅色" : "深色"}</button>)}
        </div>
        <SettingToggle label="减少动画" description="关闭位移、循环和回弹，仅保留短淡入" checked={draft.reduce_motion} onChange={() => toggle("reduce_motion")} />
      </section>
      <section className="fyt-settings-card">
        <h3>运行</h3>
        <SettingToggle label="完成后打开输出目录" description="处理成功后自动定位结果文件夹" checked={draft.auto_open_output} onChange={() => toggle("auto_open_output")} />
        <SettingToggle label="完成后弹出提示" description="业务处理成功后显示系统提示框" checked={draft.show_done_dialog} onChange={() => toggle("show_done_dialog")} />
        <SettingToggle label="启用增量缓存" description="输入和参数未变化时复用已有输出" checked={draft.enable_incremental_cache} onChange={() => toggle("enable_incremental_cache")} />
        <SettingToggle label="最小化到托盘" description="关闭主窗口时保留后台运行" checked={draft.minimize_to_tray} onChange={() => toggle("minimize_to_tray")} />
        <SettingToggle label="启动时检查更新" description="打开程序后在后台检查是否有新版本" checked={draft.check_update_on_start} onChange={() => toggle("check_update_on_start")} />
      </section>
      <section className="fyt-settings-card">
        <h3>服务器连接</h3>
        <p className="fyt-field-help">连接局域网服务器后，桌面端将像 Web 端一样使用服务器上的账号与数据；服务器界面顶部可随时返回本地模式。</p>
        <div className="fyt-inline-fields">
          <label>服务器地址<input value={serverUrl} placeholder="例如：http://192.168.1.10:8787" onChange={(event) => setServerUrl(event.target.value)} /></label>
          <button className="fyt-primary-button" disabled={!serverUrl.trim()} onClick={() => { localStorage.setItem("fyt-server-url", serverUrl.trim()); localStorage.setItem("fyt-desktop-mode", "server"); window.location.reload(); }}>保存并连接服务器</button>
        </div>
        <p className="fyt-field-help">当前为本地（离线）模式。若服务器不可达，可重新打开程序后选择本地模式。</p>
      </section>
      <section className="fyt-settings-card">
        <h3>输出目录</h3>
        <div className="fyt-segmented">
          {(["unified", "beside", "custom"] as const).map((mode) => <button key={mode} className={draft.output_mode === mode ? "active" : ""} onClick={() => setDraft({ ...draft, output_mode: mode })}>{mode === "unified" ? "统一归档" : mode === "beside" ? "源文件旁" : "自定义"}</button>)}
        </div>
        {draft.output_mode === "custom" ? <div className="fyt-custom-path-row"><input readOnly value={draft.custom_output_root} placeholder="请选择自定义输出根目录" /><button className="fyt-secondary-button" onClick={() => void chooseFiles({ title: "选择自定义输出根目录", directory: true }).then((paths) => paths[0] && setDraft({ ...draft, custom_output_root: paths[0] })).catch((reason) => setMessage(reason instanceof Error ? reason.message : String(reason)))}>选择目录</button></div> : <p className="fyt-field-help">{draft.output_mode === "unified" ? "结果统一保存到文档目录下的功能分类文件夹。" : "结果保存在第一个输入文件旁边。"}</p>}
      </section>
      <section className="fyt-settings-card">
        <h3>数据库存储</h3>
        <p className="fyt-field-help">已归档 {storage?.files ?? 0} 张表 · 占用 {Math.round((storage?.bytes ?? 0) / 1024 / 1024)} MB</p>
        <div className="fyt-settings-card-actions"><button className="fyt-secondary-button" disabled={!systemPaths?.library_dir} onClick={() => systemPaths?.library_dir && void openLocalPath(systemPaths.library_dir).catch((reason) => setMessage(String(reason)))}>打开归档目录</button><button className="fyt-secondary-button" onClick={() => void bridgeRequest<LibrarySummary>("library.summary").then((value) => setStorage({ files: Number(value.storage.files || 0), bytes: Number(value.storage.bytes || 0) }))}>刷新统计</button></div>
      </section>
      <section className="fyt-settings-card">
        <h3>增量缓存</h3>
        <p className="fyt-field-help">缓存 {cache?.entries ?? 0} 条 · 累计命中 {cache?.hits ?? 0} 次 · 索引 {Math.round((cache?.bytes ?? 0) / 1024)} KB</p>
        <div className="fyt-settings-card-actions"><button className="fyt-secondary-button" onClick={() => void bridgeRequest<typeof cache>("cache.stats").then(setCache)}>刷新统计</button><button className="fyt-secondary-button fyt-danger-button" disabled={!cache?.entries} onClick={() => void confirmAction("清除增量缓存索引？现有业务输出文件会保留。").then((confirmed) => confirmed ? bridgeRequest<{ removed: number }>("cache.clear") : null).then((result) => { if (result) { setMessage(`已清除 ${result.removed} 条缓存索引。`); setCache({ entries: 0, hits: 0, bytes: 0 }); } })}>清除缓存索引</button></div>
      </section>
      <section className="fyt-settings-card">
        <h3>系统目录</h3>
        <p className="fyt-field-help">数据目录：{systemPaths?.app_data_dir || "读取中…"}</p>
        <div className="fyt-settings-card-actions"><button className="fyt-secondary-button" disabled={!systemPaths?.app_data_dir} onClick={() => systemPaths?.app_data_dir && void openLocalPath(systemPaths.app_data_dir).catch((reason) => setMessage(String(reason)))}>打开数据目录</button><button className="fyt-secondary-button" disabled={!systemPaths?.crash_log_exists} onClick={() => systemPaths?.crash_log && void openLocalPath(systemPaths.crash_log).catch((reason) => setMessage(String(reason)))}>查看异常记录</button></div>
      </section>
      <div className="fyt-settings-actions"><span>{message}</span><button className="fyt-primary-button" onClick={() => void save()}>保存设置</button></div>
    </div>
  );
}

/** 统一设置页布尔开关的文字、说明和视觉状态，值仍由父页面受控。 */
function SettingToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: () => void }) {
  return <button className="fyt-setting-row" onClick={onChange}><span><strong>{label}</strong><small>{description}</small></span><i className={checked ? "fyt-switch on" : "fyt-switch"}><b /></i></button>;
}

/**
 * 展示本地应用版本并执行“检查清单—下载校验—用户确认安装”的更新流程。
 * 下载与摘要校验由核心层完成，真正启动安装器仍需用户确认，不会静默替换程序。
 *
 * @param health 系统健康信息；版本号缺失时回退到默认版本文案。
 * @returns 关于卡片与在线更新操作区。
 */
export function AboutPage({ health }: { health: HealthInfo | null }) {
  const [checking, setChecking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [update, setUpdate] = useState<{ version: string; notes: string; url: string; sha256?: string } | null>(null);
  const [updateMessage, setUpdateMessage] = useState("点击检查是否有新版本。");

  /** 读取更新清单并只在返回有效下载地址时保存可安装版本。 */
  async function checkUpdate() {
    setChecking(true);
    try {
      const response = await bridgeRequest<{ configured: boolean; result: null | { status: string; version?: string; notes?: string; url?: string; sha256?: string; msg?: string } }>("updater.check");
      if (!response.configured || !response.result) setUpdateMessage("更新源尚未配置。");
      else if (response.result.status === "latest") setUpdateMessage("当前已是最新版本。");
      else if (response.result.status === "update" && response.result.url) {
        setUpdate({ version: response.result.version || "新版", notes: response.result.notes || "暂无更新说明", url: response.result.url, sha256: response.result.sha256 });
        setUpdateMessage(`发现新版本 v${response.result.version}。`);
      } else setUpdateMessage(`检查失败：${response.result.msg || "更新清单无有效下载地址"}`);
    } catch (reason) { setUpdateMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setChecking(false); }
  }

  /** 下载并校验已选版本；校验成功后再次确认，才把安装包路径交给 Tauri 启动。 */
  async function downloadUpdate() {
    if (!update) return;
    setDownloading(true);
    try {
      const response = await bridgeRequest<{ result: { path: string }; logs: string[] }>("updater.download", { url: update.url, sha256: update.sha256 || "" });
      setUpdateMessage("安装包已下载并校验完成。");
      if (await confirmAction("安装包已准备完成。现在退出程序并启动安装向导吗？")) await installUpdate(response.result.path);
    } catch (reason) { setUpdateMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setDownloading(false); }
  }

  return (
    <div className="fyt-page-flow fyt-narrow-flow">
      <section className="fyt-about-card">
        <div className="fyt-about-mark">峰</div>
        <h2>峰运通数据管理系统</h2>
        <p>面向内部业务的桌面数据工作台</p>
        <dl>
          <div><dt>应用版本</dt><dd>v{health?.version ?? "1.3.0"}</dd></div>
          <div><dt>适用范围</dt><dd>峰运通内部业务</dd></div>
          <div><dt>数据安全</dt><dd>本机处理，按权限访问</dd></div>
          <div><dt>服务支持</dt><dd>可通过在线更新获取新版本</dd></div>
        </dl>
      </section>
      <section className="fyt-settings-card fyt-update-card">
        <div><h3>在线更新</h3><p>{updateMessage}</p>{update?.notes ? <pre>{update.notes}</pre> : null}</div>
        {update ? <button className="fyt-primary-button" disabled={downloading} onClick={() => void downloadUpdate()}>{downloading ? "下载并校验中…" : `下载并安装 v${update.version}`}</button> : <button className="fyt-secondary-button" disabled={checking} onClick={() => void checkUpdate()}>{checking ? "检查中…" : "检查更新"}</button>}
      </section>
    </div>
  );
}
