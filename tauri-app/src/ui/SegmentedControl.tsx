/** 支持键盘方向键、首尾跳转和禁用项跳过的分段单选控件。 */
import { useRef } from "react";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string> {
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
  label?: string;
  className?: string;
}

/**
 * 按 radiogroup 模式管理分段选项，并使用 roving tabindex 保持只有当前项进入 Tab 顺序。
 * 方向键循环查找下一个可用项，同时更新值和焦点；所有项禁用时循环自然结束而不触发
 * 无效选择。
 */
export function SegmentedControl<T extends string>({ value, options, onChange, label, className = "" }: SegmentedControlProps<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const move = (index: number, step: 1 | -1) => {
    // 最多检查选项总数，既允许首尾循环，也避免所有项禁用时形成无限循环。
    for (let offset = 0; offset < options.length; offset += 1) {
      const nextIndex = (index + offset * step + options.length) % options.length;
      const next = options[nextIndex];
      if (!next.disabled) {
        onChange(next.value);
        refs.current[nextIndex]?.focus();
        return;
      }
    }
  };

  return (
    <div className={`fyt-segmented-control ${className}`.trim()} role="radiogroup" aria-label={label}>
      {options.map((option, index) => (
        <button
          key={option.value}
          ref={(element) => { refs.current[index] = element; }}
          className="fyt-segmented-option"
          type="button"
          role="radio"
          aria-checked={option.value === value}
          tabIndex={option.value === value ? 0 : -1}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
              event.preventDefault();
              move((index + 1) % options.length, 1);
            } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
              event.preventDefault();
              move((index - 1 + options.length) % options.length, -1);
            } else if (event.key === "Home" || event.key === "End") {
              event.preventDefault();
              move(event.key === "Home" ? 0 : options.length - 1, event.key === "Home" ? 1 : -1);
            }
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default SegmentedControl;
