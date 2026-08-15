/**
 * 业务页统一页头 PageHeader。
 *
 * 负责渲染页面标题、说明、眉题和主要操作区；标题层级固定为 h1，适合每个业务页顶部
 * 只出现一次主标题的布局。具体文案与操作由页面调用方传入，本组件不感知业务模块。
 */
import type { ReactNode } from "react";

/** PageHeader 组件的输入属性。 */
export interface PageHeaderProps {
  /** 页面主标题，同时作为文档标题层级 h1。 */
  title: string;
  /** 标题下方的说明文字；缺省时不渲染说明节点。 */
  description?: string;
  /** 头部右侧的操作区内容（按钮组、搜索框等）；缺省时整块不渲染。 */
  actions?: ReactNode;
  /** 标题上方的小号眉题，用于模块或分类提示。 */
  eyebrow?: string;
}

/**
 * 渲染页面头部。
 *
 * 操作区域只在调用方提供内容时渲染，避免无操作页面保留空布局；眉题与说明同样按需
 * 渲染，保持 DOM 精简。组件本身为纯展示，不包含交互逻辑。
 *
 * @param props 见 PageHeaderProps。
 */
export function PageHeader({ title, description, actions, eyebrow }: PageHeaderProps) {
  return (
    <header className="fyt-page-header">
      <div className="fyt-page-header-copy">
        {eyebrow ? <div className="fyt-eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="fyt-page-header-actions">{actions}</div> : null}
    </header>
  );
}

export default PageHeader;
