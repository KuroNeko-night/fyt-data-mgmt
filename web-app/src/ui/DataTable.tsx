/**
 * 通用只读数据表：负责表头、加载态、空态与行渲染，
 * 不做排序、分页、筛选等交互；需要交互的数据表应在此之上再封装。
 */
import type { ReactNode } from "react";

/** 单列定义；render 存在时以函数结果为准，否则按 key 读取行字段。 */
export interface DataColumn<T> {
  /** 列键，同时作为无 render 时的字段读取路径。 */
  key: string;
  /** 表头文字。 */
  header: string;
  /** 自定义单元格渲染器，入参为当前行和行索引。 */
  render?: (row: T, index: number) => ReactNode;
  /** 追加到该列表格单元上的类名。 */
  className?: string;
}

/** 通用只读数据表属性。 */
export interface DataTableProps<T> {
  /** 列定义；只读数组保证渲染期不会被改写。 */
  columns: readonly DataColumn<T>[];
  /** 行数据；只读数组，渲染不产生副作用。 */
  rows: readonly T[];
  /** 行键生成器，默认使用行索引；有稳定业务 ID 时应显式传入。 */
  getRowKey?: (row: T, index: number) => string;
  /** 无障碍表标题，对屏幕阅读器说明表格内容。 */
  caption?: string;
  /** 加载中：先于空态展示，避免异步切换时闪出“暂无数据”。 */
  loading?: boolean;
  /** 空态提示文字，默认“暂无数据”。 */
  emptyText?: string;
  /** 追加到外层滚动容器上的类名。 */
  className?: string;
}

/**
 * 通用只读数据表。
 * 列可提供自定义 render；没有 render 时按 key 读取对象字段并安全转换成字符串。
 * @param columns 列定义，决定表头与每个单元格的渲染方式。
 * @param rows 行数据，与 columns 的 key 配合取值。
 * @param getRowKey 行键生成器；默认使用行索引，适用于无稳定 ID 的临时数据。
 * @param loading 加载中标记，优先级高于空态。
 * @param emptyText 空态提示文字。
 * @returns 外层带滚动容器的 table，加载和空态均占满全部列。
 */
export function DataTable<T>({ columns, rows, getRowKey = (_, index) => String(index), caption, loading = false, emptyText = "暂无数据", className = "" }: DataTableProps<T>) {
  return (
    <div className={`fyt-table-wrap ${className}`.trim()}>
      <table className="fyt-table">
        {caption ? <caption>{caption}</caption> : null}
        <thead><tr>{columns.map((column) => <th className={column.className} key={column.key} scope="col">{column.header}</th>)}</tr></thead>
        <tbody>
          {/* 加载态和空态都占满全部列，避免表格结构在异步切换时坍缩。 */}
          {loading ? <tr><td className="fyt-table-empty" colSpan={columns.length}>正在加载</td></tr> : rows.length === 0 ? <tr><td className="fyt-table-empty" colSpan={columns.length}>{emptyText}</td></tr> : rows.map((row, index) => <tr key={getRowKey(row, index)}>{columns.map((column) => <td className={column.className} key={column.key}>{column.render ? column.render(row, index) : /* 无 render 的列按 key 读取字段，空值统一显示为空字符串。 */ String((row as Record<string, unknown>)[column.key] ?? "")}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
