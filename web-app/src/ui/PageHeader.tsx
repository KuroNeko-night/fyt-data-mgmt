import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
}

/** 统一页面标题、眉题、说明和右侧操作区的语义结构。 */
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
