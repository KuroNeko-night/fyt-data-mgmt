/**
 * 日清接口的前向兼容归一化层。
 * 仅补齐缺失字段，不重新计算业务指标；这样 Web 服务与静态前端滚动升级时，
 * 旧响应不会因新页面访问缺失数组而导致整页崩溃。
 */
import type { DailyReportData } from "./api";

/** 将缺失或非数组字段安全归一为空数组，并保留有效数组引用。 */
function list<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

/**
 * 补齐旧版日清接口中尚未存在的区块。
 *
 * Web 服务和浏览器可能在升级期间短暂处于不同版本，前端必须把旧响应
 * 转换成当前结构，避免新增看板区块因为字段缺失而使整个日清页面崩溃。
 */
export function normalizeDailyReportData(
  raw: Partial<DailyReportData> | null | undefined,
  requestedDate: string,
): DailyReportData {
  const data = raw || {};
  const reportDate = data.date || requestedDate;
  const arrival = data.arrival || {} as Partial<DailyReportData["arrival"]>;
  const safety = data.safety_checks || {} as Partial<DailyReportData["safety_checks"]>;
  const workshop = data.workshop || {} as Partial<DailyReportData["workshop"]>;
  const attendance = data.attendance || {} as Partial<DailyReportData["attendance"]>;
  const ledger = data.production_ledger || {} as Partial<DailyReportData["production_ledger"]>;

  // 每个子区块都显式补齐，确保调用页面无需在每次遍历前重复判断字段是否存在。
  return {
    date: reportDate,
    generated_at: data.generated_at || "",
    timezone: data.timezone || "Asia/Shanghai",
    scope: "all",
    definitions: {
      arrival: data.definitions?.arrival || "当天到料批次与缺料明细",
      workshop: data.definitions?.workshop || "当天已发布的现场问题",
      safety: data.definitions?.safety || "当天安全检查与整改记录",
      production: data.definitions?.production || "当天生产计划与月度订单台账",
    },
    arrival: {
      job_count: arrival.job_count || 0,
      upload_count: arrival.upload_count || 0,
      task_count: arrival.task_count || 0,
      batch_count: arrival.batch_count || 0,
      total_categories: arrival.total_categories || 0,
      arrived_categories: arrival.arrived_categories || 0,
      missing_categories: arrival.missing_categories || 0,
      missing_material_detail_count: arrival.missing_material_detail_count || 0,
      completion_rate: arrival.completion_rate || 0,
      invalid_batch_count: arrival.invalid_batch_count || 0,
      supplier_distribution: list(arrival.supplier_distribution),
      batches: list(arrival.batches),
    },
    safety_checks: {
      upload_count: safety.upload_count || 0,
      latest_upload: safety.latest_upload || null,
      total_checks: safety.total_checks || 0,
      qualified_count: safety.qualified_count || 0,
      unqualified_count: safety.unqualified_count || 0,
      pending_count: safety.pending_count || 0,
      qualification_rate: safety.qualification_rate || 0,
      image_count: safety.image_count || 0,
      category_summary: list(safety.category_summary),
      records: list(safety.records),
      uploads: list(safety.uploads),
    },
    workshop: {
      issue_count: workshop.issue_count || 0,
      open_count: workshop.open_count ?? workshop.issue_count ?? 0, // 旧接口没有闭环状态时，把全部问题视为未闭环以保持保守口径。
      resolved_count: workshop.resolved_count || 0,
      image_count: workshop.image_count || 0,
      owner_count: workshop.owner_count || 0,
      owner_distribution: list(workshop.owner_distribution),
      category_distribution: list(workshop.category_distribution),
      issues: list(workshop.issues),
    },
    attendance: {
      people: list(attendance.people),
      production_groups: list(attendance.production_groups),
      present_count: attendance.present_count || 0,
      absent_count: attendance.absent_count || 0,
      participant_absent_count: attendance.participant_absent_count || 0,
      participant_present_count: attendance.participant_present_count || 0,
      participant_total: attendance.participant_total || 0,
      production_present_count: attendance.production_present_count || 0,
      production_total: attendance.production_total || 0,
      production_staffing_count: attendance.production_staffing_count || 0,
      production_difference: attendance.production_difference || 0,
      production_shortage_count: attendance.production_shortage_count || 0,
      production_group_count: attendance.production_group_count || 0,
      production_shift_count: attendance.production_shift_count || 0,
      unit_summary: list(attendance.unit_summary),
    },
    brief_items: list(data.brief_items),
    production_plans: list(data.production_plans),
    production_ledger: {
      month: ledger.month || reportDate.slice(0, 7), // 旧台账未返回月份时，以请求业务日期所在月兜底。
      source_file_count: ledger.source_file_count || 0,
      source_files: list(ledger.source_files),
      formal_total: ledger.formal_total || 0,
      formal_completed: ledger.formal_completed || 0,
      formal_pending: ledger.formal_pending || 0,
      formal_quantity: ledger.formal_quantity || 0,
      sporadic_total: ledger.sporadic_total || 0,
      sporadic_completed: ledger.sporadic_completed || 0,
      sporadic_pending: ledger.sporadic_pending || 0,
      sporadic_pallets: ledger.sporadic_pallets || 0,
      sporadic_volume_cbm: ledger.sporadic_volume_cbm || 0,
      missing_part_count: ledger.missing_part_count || 0,
      outstanding_missing_part_count: ledger.outstanding_missing_part_count || 0,
      hazardous_package_count: ledger.hazardous_package_count || 0,
      outstanding_hazardous_package_count: ledger.outstanding_hazardous_package_count || 0,
      today_shipments: list(ledger.today_shipments),
      formal_orders: list(ledger.formal_orders),
      sporadic_orders: list(ledger.sporadic_orders),
      missing_parts: list(ledger.missing_parts),
      hazardous_packages: list(ledger.hazardous_packages),
    },
    source_uploads: list(data.source_uploads),
  };
}
