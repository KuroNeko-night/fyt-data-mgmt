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

/** 统一展示输出文件名称、大小、权限和下载/扩展操作。 */
export function FileRow({ name, size, permission, loading = false, disabled = false, actionLabel = "下载", actions, onDownload, className = "" }: FileRowProps) {
  return (
    <div className={`fyt-file-row ${className}`.trim()}>
      <span className="fyt-file-icon" aria-hidden="true">文</span>
      <div className="fyt-file-main"><span className="fyt-file-name" title={name}>{name}</span><span className="fyt-file-meta">{size ? <span>{size}</span> : null}{permission ? <span>{permission}</span> : null}</span></div>
      <div className="fyt-file-actions">
        {actions}
        {/* 没有下载回调时不渲染空按钮，调用方仍可通过 actions 提供其他文件操作。 */}
        {onDownload ? <button className="fyt-button" data-variant="ghost" data-size="sm" type="button" onClick={onDownload} disabled={disabled || loading} aria-busy={loading || undefined}>{loading ? `${actionLabel}中` : actionLabel}</button> : null}
      </div>
    </div>
  );
}

export default FileRow;
