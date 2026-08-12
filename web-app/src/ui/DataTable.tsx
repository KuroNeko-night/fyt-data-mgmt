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
 * 通用只读数据表。
 * 列可提供自定义 render；没有 render 时按 key 读取对象字段并安全转换成字符串。
 */
export function DataTable<T>({ columns, rows, getRowKey = (_, index) => String(index), caption, loading = false, emptyText = "暂无数据", className = "" }: DataTableProps<T>) {
  return (
    <div className={`fyt-table-wrap ${className}`.trim()}>
      <table className="fyt-table">
        {caption ? <caption>{caption}</caption> : null}
        <thead><tr>{columns.map((column) => <th className={column.className} key={column.key} scope="col">{column.header}</th>)}</tr></thead>
        <tbody>
          {/* 加载态和空态都占满全部列，避免表格结构在异步切换时坍缩。 */}
          {loading ? <tr><td className="fyt-table-empty" colSpan={columns.length}>正在加载</td></tr> : rows.length === 0 ? <tr><td className="fyt-table-empty" colSpan={columns.length}>{emptyText}</td></tr> : rows.map((row, index) => <tr key={getRowKey(row, index)}>{columns.map((column) => <td className={column.className} key={column.key}>{column.render ? column.render(row, index) : String((row as Record<string, unknown>)[column.key] ?? "")}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
