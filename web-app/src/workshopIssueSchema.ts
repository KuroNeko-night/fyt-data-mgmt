/**
 * 现场问题五类规范表单的单一字段配置。
 *
 * 页面渲染、必填校验和负责人标签均从此处读取，防止不同问题类型再次显示全部字段。
 * 类别、字段和图片要求必须与核心层模板白名单同步，不在页面组件中另造问题类型。
 */
import type { WorkshopIssue, WorkshopIssueCategory } from "./api";

/**
 * 现场问题模板字段的全量键集合。
 * 所有类别共享同一张字段表，但每个类别只渲染 `sections` 中列出的子集。
 */
export type WorkshopTemplateFields = {
  issue_source: string;
  model: string;
  country: string;
  batch_no: string;
  team: string;
  material_code: string;
  material_name: string;
  cause_analysis: string;
  corrective_action: string;
  responsibility_party: string;
  external_inspection_owner: string;
  discoverer: string;
  issue_level: string;
  quantity: string;
  issue_type: string;
  completion_date: string;
  recurring: string;
  record_count: string;
  happened_at: string;
  handling_time: string;
  responsible_person: string;
  updated_by_name: string;
  carrier: string;
  supplier: string;
  tracking_status: string;
};

/** 字段键联合类型，保证模板配置里的字段名始终有对应元数据。 */
export type WorkshopTemplateFieldKey = keyof WorkshopTemplateFields;
/** 问题表单中的一个分组：图例加上该分组要展示的字段。 */
export type WorkshopFieldSection = { legend: string; fields: WorkshopTemplateFieldKey[] };

/** 单个问题类别的表单配置：分区、必填、图片要求与标签覆盖均在此声明。 */
export type WorkshopIssueFormConfig = {
  description: string;
  causeLabel: "故障描述" | "问题描述";
  causePlaceholder: string;
  sections: WorkshopFieldSection[];
  requiredFields: readonly WorkshopTemplateFieldKey[];
  requiresImages: boolean;
  allowsNotes: boolean;
  fieldLabels?: Partial<Record<WorkshopTemplateFieldKey, string>>;
};

/**
 * 现场问题五类模板的稳定键与中文名。
 * 类别键必须与核心层 workshop_issue_core.py 的模板白名单一致，前端不自行扩展类别。
 */
export const WORKSHOP_CATEGORY_OPTIONS = [
  ["main_material", "主料异常"],
  ["auxiliary_material", "辅料异常"],
  ["packaging", "包装异常"],
  ["overseas", "海外问题"],
  ["error_proofing", "防错异常"],
] as const satisfies readonly (readonly [WorkshopIssueCategory, string])[];

/**
 * 类别中文标签表，由上方选项一次性生成。
 * 下拉框、看板与详情页共用同一套名称，避免出现两处中文文案不一致。
 */
export const ISSUE_CATEGORY_LABELS: Record<WorkshopIssueCategory, string> = Object.fromEntries(
  WORKSHOP_CATEGORY_OPTIONS,
) as Record<WorkshopIssueCategory, string>;

/** 新建问题时的空表单值；补齐全部字段可避免受控输入在切换类别时出现未定义值。 */
export const EMPTY_WORKSHOP_TEMPLATE_FIELDS: WorkshopTemplateFields = {
  issue_source: "", model: "", country: "", batch_no: "", team: "", material_code: "", material_name: "",
  cause_analysis: "", corrective_action: "", responsibility_party: "", external_inspection_owner: "", discoverer: "",
  issue_level: "", quantity: "", issue_type: "", completion_date: "", recurring: "", record_count: "",
  happened_at: "", handling_time: "", responsible_person: "", updated_by_name: "",
  carrier: "", supplier: "", tracking_status: "",
};

/**
 * 字段通用元数据：只定义所有类别共用的中文标签和可选占位提示。
 * 个别类别可通过 `WorkshopIssueFormConfig.fieldLabels` 覆盖模板中的专用叫法。
 */
export const WORKSHOP_FIELD_META: Record<WorkshopTemplateFieldKey, { label: string; placeholder?: string }> = {
  issue_source: { label: "问题源", placeholder: "例如：包装过程中" },
  model: { label: "车型" }, country: { label: "国家" }, batch_no: { label: "批次号" }, team: { label: "班组" },
  material_code: { label: "物料编码" }, material_name: { label: "物料名称" },
  cause_analysis: { label: "原因分析" }, corrective_action: { label: "纠正措施" },
  responsibility_party: { label: "责任方" }, external_inspection_owner: { label: "外检责任人" }, discoverer: { label: "发现人" },
  issue_level: { label: "问题等级", placeholder: "例如：A、B、C" }, quantity: { label: "故障数量" }, issue_type: { label: "故障类别" },
  completion_date: { label: "完成时间" }, recurring: { label: "是否复发" }, record_count: { label: "记录次数" },
  happened_at: { label: "发生时间" }, handling_time: { label: "处理时间" },
  responsible_person: { label: "责任人" }, updated_by_name: { label: "更新人" }, carrier: { label: "承运商" }, supplier: { label: "供应商" },
  tracking_status: { label: "状态" },
};

/**
 * 五类现场问题的表单渲染配置。
 * `requiresImages` 遵循核心层规则：主料、辅料、包装、海外必须传图片，防错不要求；
 * `allowsNotes` 仅防错开放补充说明，避免模板外字段混入其他类别。
 */
export const WORKSHOP_ISSUE_FORM_CONFIG: Record<WorkshopIssueCategory, WorkshopIssueFormConfig> = {
  main_material: {
    description: "填写主料异常的现场信息、原因和整改结果。",
    causeLabel: "故障描述",
    causePlaceholder: "填写主料来料或运输过程中发现的故障现象",
    sections: [
      { legend: "主料信息", fields: ["model", "batch_no", "team", "material_code", "material_name"] },
      { legend: "原因与整改", fields: ["cause_analysis", "corrective_action"] },
      { legend: "问题跟进", fields: ["discoverer", "issue_level", "quantity", "issue_type", "completion_date", "recurring", "carrier", "supplier", "external_inspection_owner"] },
    ],
    requiredFields: ["discoverer"],
    requiresImages: true,
    allowsNotes: false,
  },
  auxiliary_material: {
    description: "填写辅料异常的现场信息、原因和整改结果。",
    causeLabel: "故障描述",
    causePlaceholder: "填写辅料异常的具体故障现象",
    sections: [
      { legend: "辅料信息", fields: ["issue_source", "model", "batch_no", "material_code", "material_name"] },
      { legend: "原因与整改", fields: ["cause_analysis", "corrective_action"] },
      { legend: "问题跟进", fields: ["discoverer", "issue_level", "quantity", "issue_type", "completion_date", "recurring"] },
    ],
    requiredFields: ["discoverer"],
    requiresImages: true,
    allowsNotes: false,
  },
  packaging: {
    description: "填写包装异常的现场信息、原因和整改结果。",
    causeLabel: "故障描述",
    causePlaceholder: "填写包装过程中发现的故障现象",
    sections: [
      { legend: "包装信息", fields: ["issue_source", "model", "batch_no", "team", "material_code", "material_name"] },
      { legend: "原因与整改", fields: ["cause_analysis", "corrective_action"] },
      { legend: "问题跟进", fields: ["responsibility_party", "discoverer", "issue_level", "quantity", "issue_type", "completion_date", "recurring"] },
    ],
    requiredFields: ["responsibility_party", "discoverer"],
    requiresImages: true,
    allowsNotes: false,
  },
  overseas: {
    description: "填写海外问题的车型、国家、物料和处理结果。",
    causeLabel: "问题描述",
    causePlaceholder: "填写海外反馈或发运后发现的问题",
    sections: [
      { legend: "海外问题信息", fields: ["model", "country", "batch_no", "material_code", "material_name", "quantity"] },
      { legend: "分析与整改", fields: ["cause_analysis", "corrective_action"] },
      { legend: "问题跟进", fields: ["completion_date", "responsible_person", "issue_type", "issue_level", "record_count"] },
    ],
    requiredFields: ["material_name", "responsible_person"],
    requiresImages: true,
    allowsNotes: false,
    fieldLabels: {
      quantity: "数量", corrective_action: "整改措施", responsible_person: "负责人", issue_level: "故障等级",
    },
  },
  error_proofing: {
    description: "填写防错异常的发生、处理和闭环信息。",
    causeLabel: "问题描述",
    causePlaceholder: "填写扫码、防错校验或系统识别异常",
    sections: [
      { legend: "防错信息", fields: ["happened_at", "batch_no", "material_name", "material_code"] },
      { legend: "分析与处理", fields: ["cause_analysis", "corrective_action"] },
      { legend: "处理闭环", fields: ["tracking_status", "handling_time", "responsible_person", "updated_by_name"] },
    ],
    requiredFields: ["happened_at", "tracking_status", "responsible_person"],
    requiresImages: false,
    allowsNotes: true,
    fieldLabels: { material_code: "物料号" },
  },
};

/**
 * 返回规范类别中文名，输入类型已限制为五种已维护类别。
 * @param category 已维护的现场问题类别键。
 * @returns 类别中文名，用于下拉框、标题与看板展示。
 */
export function workshopCategoryLabel(category: WorkshopIssueCategory) {
  return ISSUE_CATEGORY_LABELS[category];
}

/**
 * 根据问题类别选择模板中的责任字段和标签。
 * 海外、防错允许回退旧版 `primary_owner`，包装使用责任方，其余类别展示发现人。
 * @param issue 只取责任相关字段的问题对象。
 * @returns `[字段标签, 负责人文本]` 元组；文本可能为空，由调用方决定是否显示占位。
 */
export function workshopIssueOwnerLabel(issue: Pick<WorkshopIssue, "category" | "responsible_person" | "primary_owner" | "responsibility_party" | "discoverer">) {
  if (issue.category === "overseas") return ["负责人", issue.responsible_person || issue.primary_owner];
  if (issue.category === "error_proofing") return ["责任人", issue.responsible_person || issue.primary_owner];
  if (issue.category === "packaging") return ["责任方", issue.responsibility_party];
  return ["发现人", issue.discoverer];
}
