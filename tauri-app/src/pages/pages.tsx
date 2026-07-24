import { FormEvent, useEffect, useState } from "react";
import type { AppSettings, HealthInfo, LibrarySummary, TaskResult } from "../lib/bridge";
import { bridgeRequest, installUpdate, isTauriRuntime } from "../lib/bridge";
import { HOME_SHORTCUTS } from "../data/navigation";
import Icon from "../components/Icon";
import { chooseFiles, confirmAction, openLocalPath } from "../lib/files";

interface NavigateProps {
  navigate: (key: string) => void;
}

interface HomeProps extends NavigateProps {
  library: LibrarySummary | null;
  health: HealthInfo | null;
}

export function HomePage({ navigate, library, health }: HomeProps) {
  const total = Number(library?.storage.files ?? 0);
  return (
    <div className="page-flow">
      <section className="hero-card">
        <div className="brand-mark" aria-hidden="true">峰</div>
        <div className="hero-copy">
          <div className="hero-title-row">
            <h2>峰运通数据管理系统</h2>
            <span className="version-chip">v{health?.version ?? "1.3.0"}</span>
          </div>
          <div className="hero-rule" />
          <p>考勤、工时、销售、采购与送货业务集中处理，常用表格自动归档，处理结果统一留痕。</p>
        </div>
        <div className="hero-metric">
          <strong>{total}</strong>
          <span>已归档表格</span>
        </div>
      </section>

      <div className="section-heading">
        <div><h3>快捷入口</h3><p>从常用业务开始，Python 核心继续负责所有计算与文件生成。</p></div>
        <button className="text-button" onClick={() => navigate("tasks")}>查看任务历史</button>
      </div>

      <section className="shortcut-grid" aria-label="常用业务工作流">
        {HOME_SHORTCUTS.map((item, index) => (
          <button className="shortcut-card" key={item.key} onClick={() => navigate(item.key)}>
            <span className="shortcut-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="shortcut-icon"><Icon name={item.icon} size={22} /></span>
            <span className="shortcut-copy"><strong>{item.title}</strong><small>{item.description}</small></span>
            <span className="shortcut-arrow">›</span>
          </button>
        ))}
      </section>

      <section className="info-band">
        <div><span className="status-dot ok" /><strong>核心连接</strong><p>{isTauriRuntime() ? "Tauri 已连接 Python 业务核心" : "当前为浏览器视觉预览"}</p></div>
        <div><span className="status-dot" /><strong>运行环境</strong><p>{health?.python ?? "正在检测…"}</p></div>
        <div><span className="status-dot" /><strong>输出约定</strong><p>统一归档并保留任务历史</p></div>
      </section>
    </div>
  );
}

export function CurrencyPage() {
  const [amount, setAmount] = useState("12345.67");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    <div className="page-flow narrow-flow">
      <form className="tool-card" onSubmit={submit}>
        <label htmlFor="amount">人民币金额</label>
        <div className="input-row">
          <input id="amount" value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" autoFocus />
          <button className="primary-button" disabled={busy}>{busy ? "转换中…" : "转换为大写"}</button>
        </div>
        <p className="field-help">支持千分位、负数和两位小数，金额按“分”四舍五入。</p>
        {error ? <div className="notice error">{error}</div> : null}
        <div className="currency-result" aria-live="polite">
          <span>转换结果</span>
          <strong>{result || "输入金额后点击转换"}</strong>
          <button type="button" className="text-button" disabled={!result} onClick={() => navigator.clipboard.writeText(result)}>复制结果</button>
        </div>
      </form>
    </div>
  );
}

function formatDuration(value: number | null) {
  if (value === null) return "—";
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`;
}

export function TaskCenterPage() {
  const [data, setData] = useState<TaskResult | null>(null);
  const [error, setError] = useState("");

  async function refresh() {
    setError("");
    try { setData(await bridgeRequest<TaskResult>("tasks.list", { limit: 300 })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  useEffect(() => { void refresh(); }, []);
  async function clearFinished() {
    if (!data?.summary.total || !await confirmAction("确定清除全部已结束的任务历史吗？正在运行的任务会保留。")) return;
    try {
      const result = await bridgeRequest<{ removed: number }>("tasks.clear");
      setError(result.removed ? `已清除 ${result.removed} 条任务历史。` : "没有可清除的任务历史。");
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  async function openTaskOutput(path: string) {
    setError("");
    try { await openLocalPath(path); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  const summary = data?.summary;
  return (
    <div className="page-flow wide-flow">
      <section className="table-card">
        <div className="table-toolbar">
          <div><strong>共 {summary?.total ?? 0} 项</strong><span>运行中 {summary?.running ?? 0} · 已完成 {summary?.ok ?? 0} · 异常 {(summary?.failed ?? 0) + (summary?.interrupted ?? 0)}</span></div>
          <div className="toolbar-controls"><button className="secondary-button" onClick={() => void refresh()}>刷新</button><button className="secondary-button danger-button" disabled={!summary?.total} onClick={() => void clearFinished()}>清除已结束</button></div>
        </div>
        {error ? <div className="notice error">{error}</div> : null}
        <div className="table-scroll">
          <table>
            <thead><tr><th>状态</th><th>任务</th><th>开始时间</th><th>耗时</th><th>结果位置</th><th>说明</th></tr></thead>
            <tbody>
              {(data?.items ?? []).map((task) => (
                <tr key={task.id}>
                  <td><span className={`task-status ${task.status}`}>{task.status === "ok" ? "已完成" : task.status}</span></td>
                  <td><strong>{task.title}</strong></td>
                  <td>{task.started_at.replace("T", " ").slice(0, 19)}</td>
                  <td>{formatDuration(task.duration_ms)}</td>
                  <td className="path-cell" title={task.output_dir}>{task.output_dir ? <button className="path-button" onClick={() => void openTaskOutput(task.output_dir)}>{task.output_dir}</button> : "—"}</td>
                  <td>{task.message || "—"}</td>
                </tr>
              ))}
              {!data?.items.length ? <tr><td colSpan={6} className="empty-cell">尚无任务记录</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

interface SettingsProps {
  settings: AppSettings | null;
  onSaved: (settings: AppSettings) => void;
}

export function SettingsPage({ settings, onSaved }: SettingsProps) {
  const [draft, setDraft] = useState<AppSettings | null>(settings);
  const [message, setMessage] = useState("");
  const [systemPaths, setSystemPaths] = useState<{ app_data_dir: string; library_dir: string; default_output_root: string; crash_log: string; crash_log_exists: boolean } | null>(null);
  const [storage, setStorage] = useState<{ files: number; bytes: number } | null>(null);
  const [cache, setCache] = useState<{ entries: number; hits: number; bytes: number } | null>(null);
  useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);
  useEffect(() => {
    void Promise.all([
      bridgeRequest<typeof systemPaths>("system.paths"),
      bridgeRequest<LibrarySummary>("library.summary"),
      bridgeRequest<typeof cache>("cache.stats"),
    ]).then(([paths, library, cacheInfo]) => {
      setSystemPaths(paths); setStorage({ files: Number(library.storage.files || 0), bytes: Number(library.storage.bytes || 0) }); setCache(cacheInfo);
    }).catch((reason) => setMessage(reason instanceof Error ? reason.message : String(reason)));
  }, []);
  if (!draft) return <div className="loading-card">正在读取设置…</div>;

  async function save() {
    try {
      const updated = await bridgeRequest<AppSettings>("settings.update", { values: draft });
      setDraft(updated); onSaved(updated); setMessage("设置已保存并同步到 Python 核心。");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
  }

  const toggle = (key: keyof AppSettings) => setDraft((current) => current ? ({ ...current, [key]: !current[key] }) : current);
  return (
    <div className="page-flow narrow-flow">
      <section className="settings-card">
        <h3>外观</h3>
        <div className="segmented">
          {(["auto", "light", "dark"] as const).map((mode) => <button key={mode} className={draft.theme_mode === mode ? "active" : ""} onClick={() => setDraft({ ...draft, theme_mode: mode })}>{mode === "auto" ? "跟随系统" : mode === "light" ? "浅色" : "深色"}</button>)}
        </div>
        <SettingToggle label="减少动画" description="关闭位移、循环和回弹，仅保留短淡入" checked={draft.reduce_motion} onChange={() => toggle("reduce_motion")} />
      </section>
      <section className="settings-card">
        <h3>运行</h3>
        <SettingToggle label="完成后打开输出目录" description="处理成功后自动定位结果文件夹" checked={draft.auto_open_output} onChange={() => toggle("auto_open_output")} />
        <SettingToggle label="完成后弹出提示" description="业务处理成功后显示系统提示框" checked={draft.show_done_dialog} onChange={() => toggle("show_done_dialog")} />
        <SettingToggle label="启用增量缓存" description="输入和参数未变化时复用已有输出" checked={draft.enable_incremental_cache} onChange={() => toggle("enable_incremental_cache")} />
        <SettingToggle label="最小化到托盘" description="关闭主窗口时保留后台运行" checked={draft.minimize_to_tray} onChange={() => toggle("minimize_to_tray")} />
        <SettingToggle label="启动时检查更新" description="打开程序后在后台检查是否有新版本" checked={draft.check_update_on_start} onChange={() => toggle("check_update_on_start")} />
      </section>
      <section className="settings-card">
        <h3>输出目录</h3>
        <div className="segmented">
          {(["unified", "beside", "custom"] as const).map((mode) => <button key={mode} className={draft.output_mode === mode ? "active" : ""} onClick={() => setDraft({ ...draft, output_mode: mode })}>{mode === "unified" ? "统一归档" : mode === "beside" ? "源文件旁" : "自定义"}</button>)}
        </div>
        {draft.output_mode === "custom" ? <div className="custom-path-row"><input readOnly value={draft.custom_output_root} placeholder="请选择自定义输出根目录" /><button className="secondary-button" onClick={() => void chooseFiles({ title: "选择自定义输出根目录", directory: true }).then((paths) => paths[0] && setDraft({ ...draft, custom_output_root: paths[0] })).catch((reason) => setMessage(reason instanceof Error ? reason.message : String(reason)))}>选择目录</button></div> : <p className="field-help">{draft.output_mode === "unified" ? "结果统一保存到文档目录下的功能分类文件夹。" : "结果保存在第一个输入文件旁边。"}</p>}
      </section>
      <section className="settings-card">
        <h3>数据库存储</h3>
        <p className="field-help">已归档 {storage?.files ?? 0} 张表 · 占用 {Math.round((storage?.bytes ?? 0) / 1024 / 1024)} MB</p>
        <div className="settings-card-actions"><button className="secondary-button" disabled={!systemPaths?.library_dir} onClick={() => systemPaths?.library_dir && void openLocalPath(systemPaths.library_dir).catch((reason) => setMessage(String(reason)))}>打开归档目录</button><button className="secondary-button" onClick={() => void bridgeRequest<LibrarySummary>("library.summary").then((value) => setStorage({ files: Number(value.storage.files || 0), bytes: Number(value.storage.bytes || 0) }))}>刷新统计</button></div>
      </section>
      <section className="settings-card">
        <h3>增量缓存</h3>
        <p className="field-help">缓存 {cache?.entries ?? 0} 条 · 累计命中 {cache?.hits ?? 0} 次 · 索引 {Math.round((cache?.bytes ?? 0) / 1024)} KB</p>
        <div className="settings-card-actions"><button className="secondary-button" onClick={() => void bridgeRequest<typeof cache>("cache.stats").then(setCache)}>刷新统计</button><button className="secondary-button danger-button" disabled={!cache?.entries} onClick={() => void confirmAction("清除增量缓存索引？现有业务输出文件会保留。").then((confirmed) => confirmed ? bridgeRequest<{ removed: number }>("cache.clear") : null).then((result) => { if (result) { setMessage(`已清除 ${result.removed} 条缓存索引。`); setCache({ entries: 0, hits: 0, bytes: 0 }); } })}>清除缓存索引</button></div>
      </section>
      <section className="settings-card">
        <h3>系统目录</h3>
        <p className="field-help">数据目录：{systemPaths?.app_data_dir || "读取中…"}</p>
        <div className="settings-card-actions"><button className="secondary-button" disabled={!systemPaths?.app_data_dir} onClick={() => systemPaths?.app_data_dir && void openLocalPath(systemPaths.app_data_dir).catch((reason) => setMessage(String(reason)))}>打开数据目录</button><button className="secondary-button" disabled={!systemPaths?.crash_log_exists} onClick={() => systemPaths?.crash_log && void openLocalPath(systemPaths.crash_log).catch((reason) => setMessage(String(reason)))}>打开错误日志</button></div>
      </section>
      <div className="settings-actions"><span>{message}</span><button className="primary-button" onClick={() => void save()}>保存设置</button></div>
    </div>
  );
}

function SettingToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: () => void }) {
  return <button className="setting-row" onClick={onChange}><span><strong>{label}</strong><small>{description}</small></span><i className={checked ? "switch on" : "switch"}><b /></i></button>;
}

export function AboutPage({ health }: { health: HealthInfo | null }) {
  const [checking, setChecking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [update, setUpdate] = useState<{ version: string; notes: string; url: string; sha256?: string } | null>(null);
  const [updateMessage, setUpdateMessage] = useState("点击检查是否有新版本。");

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
    <div className="page-flow narrow-flow">
      <section className="about-card">
        <div className="brand-mark large">峰</div>
        <h2>峰运通数据管理系统</h2>
        <p>面向内部业务的桌面数据工作台</p>
        <dl>
          <div><dt>应用版本</dt><dd>v{health?.version ?? "1.3.0"}</dd></div>
          <div><dt>前端运行时</dt><dd>{isTauriRuntime() ? "Tauri 2 · React 19" : "React 浏览器预览"}</dd></div>
          <div><dt>业务核心</dt><dd>Python {health?.python ?? "检测中"}</dd></div>
          <div><dt>数据位置</dt><dd>{health?.project_root ?? "检测中"}</dd></div>
        </dl>
      </section>
      <section className="settings-card update-card">
        <div><h3>在线更新</h3><p>{updateMessage}</p>{update?.notes ? <pre>{update.notes}</pre> : null}</div>
        {update ? <button className="primary-button" disabled={downloading} onClick={() => void downloadUpdate()}>{downloading ? "下载并校验中…" : `下载并安装 v${update.version}`}</button> : <button className="secondary-button" disabled={checking} onClick={() => void checkUpdate()}>{checking ? "检查中…" : "检查更新"}</button>}
      </section>
    </div>
  );
}
