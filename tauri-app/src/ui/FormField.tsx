/** 统一标签、必填标记、帮助与错误语义的表单字段容器。 */
import type { ReactNode } from "react";

export interface FormFieldProps {
  label: string;
  htmlFor?: string;
  required?: boolean;
  help?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}

/** 错误优先于帮助文本并使用 alert 语义；控件本身由调用方通过 children 提供。 */
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
