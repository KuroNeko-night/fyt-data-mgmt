/**
 * 文件行组件：统一展示输出文件名称、大小、权限信息和下载/扩展操作。
 * 下载按钮在未提供 onDownload 时不渲染，便于纯展示场景复用。
 */
import type { ReactNode } from "react";

/** FileRow 组件属性。 */
export interface FileRowProps {
  /** 文件名，完整显示在标题属性中，超长由样式截断。 */
  name: string;
  /** 文件大小等次要信息。 */
  size?: string;
  /** 权限或可访问范围等补充信息。 */
  permission?: string;
  /** 下载中标记：按钮禁用并显示“下载中”。 */
  loading?: boolean;
  /** 禁用下载按钮，但不会隐藏调用方传入的其他操作。 */
  disabled?: boolean;
  /** 下载按钮文案，默认“下载”。 */
  actionLabel?: string;
  /** 其他扩展操作节点，渲染在下载按钮左侧。 */
  actions?: ReactNode;
  /** 下载回调；缺省时不渲染下载按钮。 */
  onDownload?: () => void;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 统一展示输出文件名称、大小、权限和下载/扩展操作。
 * @param name 文件名。
 * @param size 文件大小等元信息。
 * @param permission 权限信息。
 * @param loading 下载中标记。
 * @param disabled 是否禁用下载按钮。
 * @param actionLabel 下载按钮文案。
 * @param actions 额外操作区。
 * @param onDownload 下载回调；缺省时不渲染下载按钮。
 */
export function FileRow({ name, size, permission, loading = false, disabled = false, actionLabel = "下载", actions, onDownload, className = "" }: FileRowProps) {
  return (
    <div className={`fyt-file-row ${className}`.trim()}>
      <span className="fyt-file-icon" aria-hidden="true">文</span>
      {/* size/permission 都可选，缺省时不产生空 meta 节点。 */}
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
