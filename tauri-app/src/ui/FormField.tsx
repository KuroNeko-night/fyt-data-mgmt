/** 统一标签、必填标记、帮助与错误语义的表单字段容器。 */
import type { ReactNode } from "react";

/** 表单字段容器属性：统一标签、必填标记、帮助文本与错误语义。 */
export interface FormFieldProps {
  /** 字段名称，直接显示在控件上方。 */
  label: string;
  /** 关联控件 id，提升点击标签聚焦体验。 */
  htmlFor?: string;
  /** 是否显示必填星号；仅影响展示，不做表单校验。 */
  required?: boolean;
  /** 帮助文本，错误存在时让位于错误提示。 */
  help?: string;
  /** 错误文本；存在时以 alert 语义优先呈现。 */
  error?: string;
  /** 实际表单控件，由调用方提供。 */
  children: ReactNode;
  /** 附加到根元素的类名。 */
  className?: string;
}

/**
 * 表单字段容器：渲染标签、控件区以及错误或帮助文本。
 *
 * @param props.error 非空时优先显示错误并标记 data-invalid，帮助文本隐藏。
 * @returns 带标签关联和错误 alert 语义的字段包装元素。
 */
export function FormField({ label, htmlFor, required = false, help, error, children, className = "" }: FormFieldProps) {
  return (
    <div className={`fyt-form-field ${className}`.trim()} data-invalid={error ? "true" : undefined}>
      <label className="fyt-form-label" htmlFor={htmlFor}>
        <span>{label}</span>
        {required ? <span className="fyt-form-required" aria-hidden="true">*</span> : null}
      </label>
      <div className="fyt-form-control">{children}</div>
      {error ? <p className="fyt-form-error" role="alert">{error}</p> : help ? <p className="fyt-form-help">{help}</p> : null}
    </div>
  );
}

export default FormField;
