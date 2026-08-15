/**
 * 单选分段控件：用按钮模拟 radio 语义，实现 roving tabindex 键盘导航。
 * 视觉样式由全局分段控件类名控制，本组件只负责值、禁用态和键盘移动。
 */
import { useRef } from "react";

/** 分段控件选项；T 为业务约定的稳定字符串键。 */
export interface SegmentedOption<T extends string> {
  /** 选项值，会原样传给 onChange。 */
  value: T;
  /** 展示文字。 */
  label: string;
  /** 是否禁用；禁用项不参与键盘移动和点击。 */
  disabled?: boolean;
}

/** SegmentedControl 组件属性。 */
export interface SegmentedControlProps<T extends string> {
  /** 当前选中值，组件本身不保存状态。 */
  value: T;
  /** 选项列表；只读数组，渲染期不会修改。 */
  options: readonly SegmentedOption<T>[];
  /** 选中变化回调，接收新值。 */
  onChange: (value: T) => void;
  /** radiogroup 的可访问名称；建议与可见标题一致。 */
  label?: string;
  /** 追加到根元素的外部类名。 */
  className?: string;
}

/**
 * 可键盘操作的单选分段控件。
 * 使用 roving tabindex 保证 Tab 只进入一次，再用方向键、Home 和 End 在选项间移动。
 * @param value 当前选中值；由父组件控制，本组件是受控组件。
 * @param options 选项列表。
 * @param onChange 值变化回调。
 * @param label radiogroup 的可访问名称。
 */
export function SegmentedControl<T extends string>({ value, options, onChange, label, className = "" }: SegmentedControlProps<T>) {
  // 保存每个选项按钮的 DOM 引用，供键盘移动后直接把焦点定位到目标选项。
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  /**
   * 从给定索引沿指定方向寻找下一项未禁用选项，并同步值与焦点。
   * 方向由 step 控制：1 表示向后（右/下），-1 表示向前（左/上）。
   */
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
      {/* 按钮用 role=radio 与 aria-checked 表达单选语义；tabIndex 采用 roving 规则。 */}
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
