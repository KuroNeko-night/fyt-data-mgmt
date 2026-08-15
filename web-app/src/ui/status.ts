/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
/**
 * 状态定义总表：键为与后端协议一致的状态值，
 * 值为前端展示所需的中文标签、状态色调和短符号。
 * StatusBadge、TaskRow 等组件统一消费该表，避免各处硬编码状态文案。
 */
export const STATUS_DEFINITIONS = {
  "queued": {
    "label": "排队",
    "tone": "warning",
    "symbol": "等待"
  },
  "running": {
    "label": "处理中",
    "tone": "info",
    "symbol": "进行"
  },
  "review": {
    "label": "待确认",
    "tone": "warning",
    "symbol": "确认"
  },
  "completed": {
    "label": "已完成",
    "tone": "success",
    "symbol": "完成"
  },
  "failed": {
    "label": "异常",
    "tone": "danger",
    "symbol": "异常"
  },
  "cancelled": {
    "label": "已取消",
    "tone": "neutral",
    "symbol": "取消"
  },
  "interrupted": {
    "label": "已中断",
    "tone": "danger",
    "symbol": "中断"
  }
} as const;
/** 状态键：从 STATUS_DEFINITIONS 推导，保证与后端协议枚举同步。 */
export type StatusKey = keyof typeof STATUS_DEFINITIONS;
/** 状态色调：从 STATUS_DEFINITIONS 推导，供样式 data-tone 使用。 */
export type StatusTone = (typeof STATUS_DEFINITIONS)[StatusKey]["tone"];
