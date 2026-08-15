/** 文件名、容量、权限和操作按钮的统一列表行。 */
import type { ReactNode } from "react";

/** 文件列表行属性：统一展示文件名、元信息与操作入口。 */
export interface FileRowProps {
  /** 显示用文件名；完整路径通过 title 提示呈现。 */
  name: string;
  /** 可选容量或大小文本，由调用方预先格式化。 */
  size?: string;
  /** 可选权限/状态文本，展示在大小之后。 */
  permission?: string;
  /** 下载进行中；为 true 时禁用按钮并切换进行中文案。 */
  loading?: boolean;
  /** 常规禁用状态，与 loading 按“或”关系合并。 */
  disabled?: boolean;
  /** 下载按钮文案，默认“下载”。 */
  actionLabel?: string;
  /** 调用方插入的额外操作节点，与下载按钮位于同一操作区。 */
  actions?: ReactNode;
  /** 下载回调；未提供时整个下载按钮不渲染。 */
  onDownload?: () => void;
  /** 附加到根元素的类名。 */
  className?: string;
}

/**
 * 文件列表行：左侧文件图标与名称，右侧操作区，元信息为空时自动省略。
 *
 * @param props.onDownload 提供后渲染下载按钮；loading 时按钮禁用并显示“下载中”。
 * @returns 单行文件信息；下载入口与调用方额外操作共享同一容器。
 */
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
