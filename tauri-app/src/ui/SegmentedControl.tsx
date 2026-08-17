/**
 * 分段单选控件 SegmentedControl。
 *
 * 支持键盘方向键、首尾跳转和禁用项跳过的分段单选控件；用于选项数量有限的单选切换，
 * 状态由受控属性 value 驱动，选择结果通过 onChange 回传，组件自身不保存选中状态。
 */
import { useRef } from "react";

/** 单个分段选项。泛型 T 约束为 string，保证选项值可作为 key 与 ARIA 选中比较。 */
export interface SegmentedOption<T extends string> {
  /** 选项值，回传给 onChange 的唯一标识。 */
  value: T;
  /** 展示给用户的文案。 */
  label: string;
  /** 是否禁用；禁用项保留可见但不可聚焦、不可选择。 */
  disabled?: boolean;
}

/** SegmentedControl 组件的输入属性。 */
export interface SegmentedControlProps<T extends string> {
  /** 当前选中值，组件完全受控。 */
  value: T;
  /** 可选项列表；顺序决定显示顺序和键盘移动顺序。 */
  options: readonly SegmentedOption<T>[];
  /** 用户点击或键盘确认选择后的回调。 */
  onChange: (value: T) => void;
  /** radiogroup 的无障碍名称。 */
  label?: string;
  /** 追加到容器上的自定义类名。 */
  className?: string;
}

/**
 * 渲染分段单选控件。
 *
 * 按 radiogroup 模式管理分段选项，并使用 roving tabindex 保持只有当前项进入 Tab 顺序：
 * 键盘焦点始终跟随选中项，方向键移动到的新选项会同时更新值和焦点。方向键循环查找
 * 下一个可用项；所有项禁用时循环自然结束而不触发无效选择。
 *
 * @param props 见 SegmentedControlProps。
 */
export function SegmentedControl<T extends string>({ value, options, onChange, label, className = "" }: SegmentedControlProps<T>) {
  // 保存每个选项按钮的 DOM 引用，便于键盘移动后把焦点同步到新选中项。
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const move = (index: number, step: 1 | -1) => {
    // 最多检查选项总数，既允许首尾循环，也避免所有项禁用时形成无限循环。
    for (let offset = 0; offset < options.length; offset += 1) {
      const nextIndex = (index + offset * step + options.length) % options.length;  // 循环查找并跳过禁用项，避免全部禁用时死循环
      const next = options[nextIndex];
      if (!next.disabled) {
        onChange(next.value);
        refs.current[nextIndex]?.focus();
        return;
      }
    }
  };

  // 渲染为 radiogroup；只有当前选中项 tabIndex=0，其余项通过方向键可达（roving tabindex）。
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
            // 右/下方向键向后移动，左/上方向键向前移动；Home/End 直接跳到首/尾。
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
