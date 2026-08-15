/** 支持泛型行、自定义单元格、加载态和空态的轻量业务表格。 */
import type { ReactNode } from "react";

/** 数据表格列定义。 */
export interface DataColumn<T> {
  /** 字段键；未提供 render 时按此键从行对象读取普通值。 */
  key: string;
  /** 表头文案。 */
  header: string;
  /** 自定义单元格渲染器，参数为当前行与行号。 */
  render?: (row: T, index: number) => ReactNode;
  /** 附加到该列 th/td 的类名。 */
  className?: string;
}

/** 数据表格属性。 */
export interface DataTableProps<T> {
  /** 列定义；render 缺省时按 key 读取普通值。 */
  columns: readonly DataColumn<T>[];
  /** 行数据，按原顺序渲染。 */
  rows: readonly T[];
  /** 行键计算函数，默认使用行号。 */
  getRowKey?: (row: T, index: number) => string;
  /** 表格说明，供辅助技术读取且视觉隐藏。 */
  caption?: string;
  /** 加载态；为 true 时用单行“正在加载”覆盖表体。 */
  loading?: boolean;
  /** 空数据文案，默认“暂无数据”。 */
  emptyText?: string;
  /** 附加到外层滚动容器的类名。 */
  className?: string;
}

/**
 * 使用调用方提供的稳定行键和列定义渲染表格；未提供渲染器时按字段键读取普通值。
 * `caption` 会保留给辅助技术，加载态与空态都使用覆盖全列的单行结构，避免表头抖动。
 *
 * @template T 行数据类型。
 * @param columns 列定义；render 缺省时按字段键读取普通值。
 * @param rows 要展示的行数据。
 * @param getRowKey 行键计算函数，默认使用行号作为 React key。
 * @param caption 辅助技术表格说明。
 * @param loading 加载态；为 true 时表体仅展示加载行。
 * @param emptyText 空数据文案。
 * @returns 外层带滚动容器的表格；加载态与空态均使用单行结构。
 */
export function DataTable<T>({ columns, rows, getRowKey = (_, index) => String(index), caption, loading = false, emptyText = "暂无数据", className = "" }: DataTableProps<T>) {
  return (
    <div className={`fyt-table-wrap ${className}`.trim()}>
      <table className="fyt-table">
        {caption ? <caption>{caption}</caption> : null}
        <thead><tr>{columns.map((column) => <th className={column.className} key={column.key} scope="col">{column.header}</th>)}</tr></thead>
        <tbody>
          {loading ? <tr><td className="fyt-table-empty" colSpan={columns.length}>正在加载</td></tr> : rows.length === 0 ? <tr><td className="fyt-table-empty" colSpan={columns.length}>{emptyText}</td></tr> : rows.map((row, index) => <tr key={getRowKey(row, index)}>{columns.map((column) => <td className={column.className} key={column.key}>{column.render ? column.render(row, index) : String((row as Record<string, unknown>)[column.key] ?? "")}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
