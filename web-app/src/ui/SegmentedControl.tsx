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
 * 可键盘操作的单选分段控件。
 * 使用 roving tabindex 保证 Tab 只进入一次，再用方向键、Home 和 End 在选项间移动。
 */
export function SegmentedControl<T extends string>({ value, options, onChange, label, className = "" }: SegmentedControlProps<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  /** 从给定索引沿指定方向寻找下一项未禁用选项，并同步值与焦点。 */
  const move = (index: number, step: 1 | -1) => {
    for (let offset = 0; offset < options.length; offset += 1) {
      // 加 options.length 后取模，使左右移动能够在首尾之间循环。
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
          tabIndex={option.value === value ? 0 : -1} // radiogroup 内只有当前项进入页面 Tab 顺序。
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
