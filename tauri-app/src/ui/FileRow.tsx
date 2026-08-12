/** 文件名、容量、权限和操作按钮的统一列表行。 */
import type { ReactNode } from "react";

export interface FileRowProps {
  name: string;
  size?: string;
  permission?: string;
  loading?: boolean;
  disabled?: boolean;
  actionLabel?: string;
  actions?: ReactNode;
  onDownload?: () => void;
  className?: string;
}

/** 下载进行中自动禁用按钮并改变客户文案，额外操作由调用方插入同一操作区。 */
export function FileRow({ name, size, permission, loading = false, disabled = false, actionLabel = "下载", actions, onDownload, className = "" }: FileRowProps) {
  return (
    <div className={`fyt-file-row ${className}`.trim()}>
      <span className="fyt-file-icon" aria-hidden="true">文</span>
      <div className="fyt-file-main"><span className="fyt-file-name" title={name}>{name}</span><span className="fyt-file-meta">{size ? <span>{size}</span> : null}{permission ? <span>{permission}</span> : null}</span></div>
      <div className="fyt-file-actions">
        {actions}
        {onDownload ? <button className="fyt-button" data-variant="ghost" data-size="sm" type="button" onClick={onDownload} disabled={disabled || loading} aria-busy={loading || undefined}>{loading ? `${actionLabel}中` : actionLabel}</button> : null}
      </div>
    </div>
  );
}

export default FileRow;
