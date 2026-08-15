/** 把 Core 的统一业务结果投影渲染为指标、可信度、参数、提示和明细表。 */
import type { BusinessResultPresentation } from "../hooks/useBridgeTask";
import DataTable from "./DataTable";
import Notice from "./Notice";

/**
 * 将业务结果色调归一为 Notice 组件支持的四种语义。
 *
 * @param tone Core 投影色调，可能是 danger/success/warning 或未知值。
 * @returns Notice 可识别的 info/success/warning/error 四态。
 */
function noticeTone(tone: string): "info" | "success" | "warning" | "error" {
  return tone === "danger" ? "error" : tone === "success" ? "success" : tone === "warning" ? "warning" : "info";
}

/**
 * 只消费 `business_result_core` 生成的结构化投影，不在前端重新分析输出文件。
 *
 * 明细列和指标顺序由 Core 决定；截断提示明确区分页面预览与正式报告。可信度采用原生
 * progressbar 语义并保留每项核查依据，便于人工复核处理结论。
 *
 * @param presentation Core 层统一业务结果投影，含指标、质量、参数、提示和明细。
 * @returns 结果区块；质量、参数等模块按投影是否提供而选择渲染。
 */
export function BusinessResultView({ presentation }: { presentation: BusinessResultPresentation }) {
  const quality = presentation.quality;
  // 兼容尚未提供可调参数投影的旧业务结果，避免参数区渲染失败。
  const parameters = presentation.parameters || [];
  return <section className="fyt-business-result" aria-label={presentation.title}>
    <header className="fyt-business-result-head">
      <div><span>业务结果</span><h3>{presentation.title}</h3></div>
      <p>{presentation.summary}</p>
    </header>
    {presentation.metrics.length ? <div className="fyt-business-result-metrics" role="list" aria-label="结果指标">
      {presentation.metrics.map((metric) => <div key={metric.key} role="listitem" data-tone={metric.tone}>
        <span>{metric.label}</span><strong>{metric.value}</strong>{metric.note ? <small>{metric.note}</small> : null}
      </div>)}
    </div> : null}
    {quality ? <section className="fyt-business-quality" data-tone={quality.tone} aria-label="可信度与核查依据">
      <div className="fyt-business-quality-score"><span>可信度</span><strong>{quality.score}</strong><small>/ 100 · {quality.level}</small></div>
      <div className="fyt-business-quality-body"><div className="fyt-business-quality-track" role="progressbar" aria-label={`可信度 ${quality.score} 分`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={quality.score}><i style={{ width: `${quality.score}%` }} /></div><p>{quality.summary}</p>{quality.checks.length ? <div className="fyt-business-quality-checks">{quality.checks.map((check, index) => <article data-tone={check.tone} key={`${check.title}-${index}`}><span /><div><strong>{check.title}</strong><p>{check.message}</p></div></article>)}</div> : null}</div>
    </section> : null}
    {parameters.length ? <section className="fyt-business-parameters" aria-label="本次采用设置"><div className="fyt-business-parameters-title"><strong>本次采用设置</strong><span>便于复核处理口径</span></div><div>{parameters.map((item) => <span key={item.key}><small>{item.label}</small><strong>{item.value || "未设置"}</strong></span>)}</div></section> : null}
    {presentation.notices.map((notice, index) => <Notice tone={noticeTone(notice.tone)} key={`${notice.title}-${index}`} title={notice.title}>{notice.message}</Notice>)}
    {presentation.sections.map((section) => <section className="fyt-business-result-section" key={section.key}>
      <div className="fyt-business-result-section-head"><div><h4>{section.title}</h4>{section.description ? <p>{section.description}</p> : null}</div><span>{section.total} 条</span></div>
      {/* 明细列由 Core 投影按业务顺序给出；此处只映射标题与取值键，避免前端重新定义列语义。 */}
      <DataTable columns={section.columns.map((column) => ({ key: column.key, header: column.label }))} rows={section.rows} caption={`${section.title}，共 ${section.total} 条`} emptyText="没有需要展示的明细" />
      {section.truncated ? <p className="fyt-business-result-more">页面先显示前 {section.rows.length} 条，完整 {section.total} 条请查看正式输出报告。</p> : null}
    </section>)}
  </section>;
}

export default BusinessResultView;
