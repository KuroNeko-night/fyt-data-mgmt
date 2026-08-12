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

/** 通用表单字段容器，统一标签、必填标记、帮助文本和错误优先级。 */
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
