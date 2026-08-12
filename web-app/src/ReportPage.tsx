import { useState } from "react";
import { buildReport } from "./api";
import { Icon } from "./icons";
import DataTable from "./ui/DataTable";
import FileRow from "./ui/FileRow";
import PageHeader from "./ui/PageHeader";

/** 按时间范围和账号范围生成任务汇总 Excel 报表。 */
export function ReportPage() {
  const [range, setRange] = useState<"7d" | "30d" | "month" | "all">("30d");
  const [scopeAll, setScopeAll] = useState(false);
  const [result, setResult] = useState<{ url: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // 结果生成后保留本次请求参数，便于管理员下载前再次核对统计口径。
  const summaryRows = result ? [
    { label: "统计范围", value: range === "7d" ? "近 7 天" : range === "30d" ? "近 30 天" : range === "month" ? "本月" : "全部" },
    { label: "统计对象", value: scopeAll ? "全部账号" : "当前账号" },
    { label: "文件状态", value: "已生成，可下载" },
  ] : [];
  /** 请求服务端生成报表；开始新请求时清除旧结果，避免误下载上一轮文件。 */
  async function build() {
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await buildReport(range, scopeAll));
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
      {result ? <div className="fyt-report-result"><span>报表已生成</span><FileRow name={result.name} permission="当前账号可下载" onDownload={() => { const link = document.createElement("a"); link.href = result.url; link.download = result.name; link.click(); }} /><DataTable columns={[{ key: "label", header: "项目" }, { key: "value", header: "本次结果" }]} rows={summaryRows} caption="本次报表参数" /></div> : null}
    </div>
  </div>;
}
