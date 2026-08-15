/**
 * 表单字段容器：统一标签、必填星号、帮助文本与错误信息的位置和优先级。
 * 只负责包装结构与可访问性，不接管子控件的值或事件。
 */
import type { ReactNode } from "react";

/** FormField 组件属性。 */
export interface FormFieldProps {
  /** 字段标签文字。 */
  label: string;
  /** 关联的控件 id，点击标签可聚焦控件。 */
  htmlFor?: string;
  /** 必填标记；星号为纯视觉提示，必填校验仍由业务层执行。 */
  required?: boolean;
  /** 帮助文本，错误出现时被取代。 */
  help?: string;
  /** 错误信息；存在时字段标记为 invalid，并以 role=alert 朗读。 */
  error?: string;
  /** 表单控件。 */
  children: ReactNode;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 通用表单字段容器，统一标签、必填标记、帮助文本和错误优先级。
 * @param label 标签文字。
 * @param htmlFor 关联控件 id。
 * @param required 是否显示必填星号。
 * @param help 帮助文本，仅在没有错误时展示。
 * @param error 错误信息，优先级高于帮助文本。
 * @param children 表单控件。
 */
export function FormField({ label, htmlFor, required = false, help, error, children, className = "" }: FormFieldProps) {
  return (
    <div className={`fyt-form-field ${className}`.trim()} data-invalid={error ? "true" : undefined}>
      <label className="fyt-form-label" htmlFor={htmlFor}>
        <span>{label}</span>
        {required ? <span className="fyt-form-required" aria-hidden="true">*</span> : null}
      </label>
      <div className="fyt-form-control">{children}</div>
      {/* 错误出现时取代帮助文本，避免同一字段底部同时出现两条互相竞争的信息。 */}
      {error ? <p className="fyt-form-error" role="alert">{error}</p> : help ? <p className="fyt-form-help">{help}</p> : null}
    </div>
  );
}

export default FormField;
