/**
 * 页面标题组件：统一页首的眉题、标题、说明和右侧操作区的语义结构，
 * 供各业务模块页面保持一致的信息层级。
 */
import type { ReactNode } from "react";

/** PageHeader 组件属性。 */
export interface PageHeaderProps {
  /** 页面主标题，渲染为 h1。 */
  title: string;
  /** 标题下的补充说明。 */
  description?: string;
  /** 右侧操作区，通常放主要按钮。 */
  actions?: ReactNode;
  /** 眉题，渲染在标题上方的小号提示文字。 */
  eyebrow?: string;
}

/**
 * 统一页面标题、眉题、说明和右侧操作区的语义结构。
 * @param title 主标题。
 * @param description 补充说明。
 * @param actions 右侧操作区。
 * @param eyebrow 眉题。
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
