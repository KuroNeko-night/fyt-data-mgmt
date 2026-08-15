/**
 * 批次跟踪页面。
 *
 * 通过服务端跨任务检索同一批次号在考勤、到料、对账、采购等环节的处理记录，
 * 前端只负责展示动作中文名与状态，不参与批次解析或结果文件内容读取。
 */
import { FormEvent, useState } from "react";
import { batchTrack, type BatchTrackItem } from "./api";
import { Icon } from "./icons";
import PageHeader from "./ui/PageHeader";

// 服务端动作键到客户界面业务名称的映射；未知动作由调用方回退为“业务处理”。
const ACTION_LABELS: Record<string, string> = {
  "attendance.run": "考勤填报", "reconcile.run": "工时对账", "web.reconcile.review": "工时对账复核",
  "web.arrival": "到料明细", "pivot.run": "销售透视", "web.pivot.review": "销售透视复核",
  "purchase.run": "采购对账", "shipping_review.run": "发运评审对比", "delivery.run": "送货计划", "supplier_batch.run": "供应商批次表",
  "web.supplier_batch.review": "供应商批次表复核", "purchase_plan.run": "采购计划导入",
  "web.invoice": "发票统计", "rename.apply": "批量重命名", "text.transform": "文本工具",
  "pdf.run": "PDF 工具", "excel.run": "Excel 工具", "web.compare": "表格比对",
};

/** 把批次关联任务状态转换为客户界面文案。 */
function statusLabel(status: string) {
  const labels: Record<string, string> = { completed: "已完成", running: "处理中", failed: "处理失败", queued: "排队中", cancelled: "已取消", interrupted: "已中断" };
  return labels[status] || "未知状态";
}

/** 按批次关键词跨业务任务检索处理记录和输出文件名。 */
export function BatchTrackPage() {
  const [keyword, setKeyword] = useState("");
  const [items, setItems] = useState<BatchTrackItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  /** 提交修剪后的批次号；searched 单独记录是否应展示空结果。 */
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!keyword.trim()) return;
    setBusy(true); setError(""); setSearched(true);
    try {
      const result = await batchTrack(keyword.trim());
      setItems(result.items);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "搜索失败"); }
    finally { setBusy(false); }
  }
  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-batch-page">
    <PageHeader eyebrow="全流程跟踪" title="批次跟踪" description="输入批次号（如 26036-02、26178A），查看该批次在各业务环节的处理记录与结果文件。" />
    <form className="fyt-batch-search" onSubmit={(event) => void search(event)}><Icon name="search" size={16} /><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入批次号，例如 26036-02" /><button type="submit" disabled={busy || !keyword.trim()}>{busy ? "搜索中" : "搜索"}</button></form>
    {error ? <div className="fyt-notice fyt-notice-error" role="alert">{error}</div> : null}
    {searched && !busy && !error ? <div className="fyt-batch-results">
      {items.length ? items.map((item) => <article className="fyt-batch-result-row" key={item.job_id}><div className={`fyt-batch-result-icon ${item.status}`}><Icon name={item.status === "completed" ? "check" : item.status === "failed" ? "x" : "activity"} size={17} /></div><div className="fyt-batch-result-main"><div className="fyt-batch-result-title"><strong>{ACTION_LABELS[item.action] || "业务处理"}</strong><span className={`fyt-batch-result-status ${item.status}`}><i />{statusLabel(item.status)}</span></div><small>{new Date(item.created_at).toLocaleString("zh-CN")} · {item.title}{item.files.length ? ` · 结果：${item.files.join("、")}` : ""}</small></div></article>) : <div className="fyt-empty-state"><img src="/illustrations/search-results.svg" alt="" /><span>没有找到与「{keyword.trim()}」相关的任务记录</span></div>}
    </div> : null}
  </div>;
}
