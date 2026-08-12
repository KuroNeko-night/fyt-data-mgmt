/** 支持泛型行、自定义单元格、加载态和空态的轻量业务表格。 */
import type { ReactNode } from "react";

export interface DataColumn<T> {
  key: string;
  header: string;
  render?: (row: T, index: number) => ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  columns: readonly DataColumn<T>[];
  rows: readonly T[];
  getRowKey?: (row: T, index: number) => string;
  caption?: string;
  loading?: boolean;
  emptyText?: string;
  className?: string;
}

/**
 * 使用调用方提供的稳定行键和列定义渲染表格；未提供渲染器时按字段键读取普通值。
 * `caption` 会保留给辅助技术，加载态与空态都使用覆盖全列的单行结构，避免表头抖动。
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
