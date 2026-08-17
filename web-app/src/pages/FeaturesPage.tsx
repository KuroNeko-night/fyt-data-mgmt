import { useMemo } from "react";
import type { Feature } from "../api";
import { Icon } from "../icons";
import Button from "../ui/Button";
import PageHeader from "../ui/PageHeader";
import Surface from "../ui/Surface";

/**
 * 按服务端提供的业务分组归并模块，并保留模块原始顺序。
 * @param features 服务端返回的当前账号可用功能列表。
 * @returns `[分组名, 该分组功能列表]` 数组；分组顺序取首次出现顺序。
 */
function groupFeatures(features: Feature[]) {
  return Array.from(features.reduce((groups, feature) => {
    const current = groups.get(feature.group) || [];
    current.push(feature);
    groups.set(feature.group, current);
    return groups;
  }, new Map<string, Feature[]>()).entries());
}

/**
 * 业务模块总览页：以分组卡片展示当前账号有权使用的功能。
 * @param features 当前账号有权使用的业务模块；空列表时显示空态。
 * @param onOpen 点击“打开模块”后进入具体业务工作区。
 */
export function FeaturesPage({ features, onOpen }: { features: Feature[]; onOpen: (key: string) => void }) {
  // 功能列表通常来自服务端配置，分组结果按列表引用缓存即可。
  const groups = useMemo(() => groupFeatures(features), [features]);  // 功能列表来自服务端配置，按引用缓存分组结果
  return <div className="fyt-feature-page">
    <PageHeader eyebrow="业务能力" title="业务模块" description="选择要处理的资料，系统会依次完成检查、处理和结果生成。" />
    {groups.length ? <div className="fyt-feature-groups">{groups.map(([group, items]) => <Surface as="section" variant="subtle" className="fyt-feature-group" key={group}>
      <header className="fyt-feature-group-head"><h2>{group}</h2><span>{items.length} 个模块</span></header>
      <div className="fyt-feature-list">{items.map((feature, index) => <article className="fyt-feature-card" key={feature.key}>
        <div className="fyt-feature-card-head"><span className="fyt-feature-index">{String(index + 1).padStart(2, "0")}</span><Icon name={index % 2 ? "activity" : "database"} size={20} /></div>
        <h3>{feature.title}</h3>
        <p>{feature.description}</p>
        <Button variant="secondary" size="sm" type="button" onClick={() => onOpen(feature.key)}>打开模块 <Icon name="arrow" size={15} /></Button>
      </article>)}</div>
    </Surface>)}</div> : <div className="fyt-empty-state"><span className="fyt-empty-icon"><Icon name="database" size={18} /></span><h3>暂无可用业务模块</h3><p>当前账号还没有可用的业务处理入口。</p></div>}
  </div>;
}

export default FeaturesPage;
