/** 业务页标题、说明、眉题和主要操作的统一页头。 */
import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
}

/** 操作区域只在调用方提供内容时渲染，避免无操作页面保留空布局。 */
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
