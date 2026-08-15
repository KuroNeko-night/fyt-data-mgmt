import type { BusinessResultPresentation } from "./api";
import DataTable from "./ui/DataTable";
import Notice from "./ui/Notice";

/**
 * 把业务投影层的 danger 色调适配为通用 Notice 使用的 error 名称。
 * @param tone 服务端投影返回的指标或提示色调。
 * @returns Notice 组件可识别的色调；未知值一律按 info 降级，避免渲染分支缺失。
 */
function noticeTone(tone: string): "info" | "success" | "warning" | "error" {
  return tone === "danger" ? "error" : tone === "success" ? "success" : tone === "warning" ? "warning" : "info";
}

/**
 * 渲染 core/business_result_core.py 生成的统一业务结果投影。
 * 指标、可信度、参数和明细均由服务端计算，前端不重新解释输出工作簿。
 * @param props.presentation 服务端生成的结构化业务结果；前端只负责展示与降级。
 */
export function BusinessResultView({ presentation }: { presentation: BusinessResultPresentation }) {
  const quality = presentation.quality;
  const parameters = presentation.parameters || []; // 兼容尚未提供可调参数投影的旧任务结果。
  // 各分区均按“有数据才渲染”处理，旧任务缺字段时只少显示一个区块，不会产生空壳节点。
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
      <DataTable columns={section.columns.map((column) => ({ key: column.key, header: column.label }))} rows={section.rows} caption={`${section.title}，共 ${section.total} 条`} emptyText="没有需要展示的明细" />
      {section.truncated ? <p className="fyt-business-result-more">页面先显示前 {section.rows.length} 条，完整 {section.total} 条请查看正式输出报告。</p> : null}
    </section>)}
  </section>;
}

export default BusinessResultView;
