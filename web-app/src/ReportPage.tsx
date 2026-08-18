/**
 * 报表中心页面。
 *
 * 按时间范围和账号范围请求服务端生成任务汇总 Excel；普通成员只能统计
 * 自己的任务，管理员可选择全量统计，最终口径由服务端接口控制。
 */
import { useEffect, useState } from "react";
import { buildReport, listReports } from "./api";
import { Icon } from "./icons";
import DataTable from "./ui/DataTable";
import FileRow from "./ui/FileRow";
import PageHeader from "./ui/PageHeader";

/** 按时间范围和账号范围生成任务汇总 Excel 报表。 */
export function ReportPage() {
  const [range, setRange] = useState<"7d" | "30d" | "month" | "all">("30d");
  const [scopeAll, setScopeAll] = useState(false);
  const [result, setResult] = useState<{ url: string; name: string } | null>(null);
  const [reports, setReports] = useState<Awaited<ReturnType<typeof listReports>>["reports"]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // 结果生成后保留本次请求参数，便于管理员下载前再次核对统计口径。
  const summaryRows = result ? [
    { label: "统计范围", value: range === "7d" ? "近 7 天" : range === "30d" ? "近 30 天" : range === "month" ? "本月" : "全部" },
    { label: "统计对象", value: scopeAll ? "全部账号" : "当前账号" },
    { label: "文件状态", value: "已生成，可下载" },
  ] : [];
  /** 报表中心进入时加载自动和手动生成的历史文件，后端负责目录与权限过滤。 */
  useEffect(() => {
    let active = true;
    void listReports().then((payload) => {
      if (active) setReports(payload.reports);
    }).catch((reason) => {
      if (active) setHistoryError(reason instanceof Error ? reason.message : "历史报表加载失败");
    }).finally(() => {
      if (active) setHistoryLoading(false);
    });
    return () => { active = false; };
  }, []);

  function download(url: string, name: string) {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
  /** 请求服务端生成报表；开始新请求时清除旧结果，避免误下载上一轮文件。 */
  async function build() {
    setBusy(true); setError(""); setResult(null);  // 新请求开始即清空旧结果，避免误下载上一轮文件
    try {
      const created = await buildReport(range, scopeAll);
      setResult(created);
      // 生成接口成功后刷新列表，使新文件和自动生成文件使用同一展示口径。
      const latest = await listReports();
      setReports(latest.reports);
      setHistoryError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "生成失败"); }
    finally { setBusy(false); }
  }
  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-report-page">
    <PageHeader eyebrow="数据汇总" title="报表中心" description="按时间范围汇总各业务模块的任务记录，生成可打印的 Excel 报表（任务汇总、模块分布与明细）。" />
    <div className="fyt-report-panel">
      <div className="fyt-report-head"><div><h3>生成业务报表</h3><p>普通用户统计自己的任务，管理员可选择全量统计。</p></div></div>
      <div className="fyt-report-range" role="tablist" aria-label="报表时间范围">
        {([["7d", "近 7 天"], ["30d", "近 30 天"], ["month", "本月"], ["all", "全部"]] as const).map(([key, label]) => <button type="button" key={key} className={range === key ? "selected" : ""} aria-selected={range === key} onClick={() => setRange(key)}>{label}</button>)}
      </div>
      <label className="fyt-report-scope"><input type="checkbox" checked={scopeAll} onChange={(event) => setScopeAll(event.target.checked)} />统计全部账号（仅管理员可用）</label>
      <div className="fyt-row-actions"><button type="button" className="fyt-action-primary" disabled={busy} onClick={() => void build()}>{busy ? "生成中..." : "生成报表"}<Icon name="arrow" size={16} /></button></div>
      {error ? <div className="fyt-notice fyt-notice-error" role="alert">{error}</div> : null}
      {result ? <div className="fyt-report-result"><span>报表已生成</span><FileRow name={result.name} permission="当前账号可下载" onDownload={() => download(result.url, result.name)} /><DataTable columns={[{ key: "label", header: "项目" }, { key: "value", header: "本次结果" }]} rows={summaryRows} caption="本次报表参数" /></div> : null}
    </div>
    <section className="fyt-report-history" aria-labelledby="report-history-title">
      <div className="fyt-report-head"><div><h3 id="report-history-title">历史报表</h3><p>自动生成的周报、月报和手动生成的报表都会保存在这里。</p></div><span className="fyt-report-history-count">最近 {reports.length} 份</span></div>
      {historyError ? <div className="fyt-notice fyt-notice-error" role="alert">{historyError}</div> : null}
      {historyLoading ? <div className="fyt-empty-state"><span>正在加载历史报表…</span></div> : reports.length ? <div className="fyt-report-history-list">{reports.map((report) => <FileRow key={`${report.url}-${report.generated_at}`} name={report.name} size={formatSize(report.size)} permission={`${report.scope_label} · ${formatDate(report.generated_at)}`} onDownload={() => download(report.url, report.name)} />)}</div> : <div className="fyt-empty-state"><span>还没有可下载的历史报表</span><small>生成一次业务报表后，文件会自动出现在这里。</small></div>}
    </section>
  </div>;
}

function formatSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
