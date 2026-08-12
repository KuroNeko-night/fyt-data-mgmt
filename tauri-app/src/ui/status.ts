/* 此文件由 scripts/sync-design-tokens.mjs 生成，请勿手工修改。 */
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
export type StatusKey = keyof typeof STATUS_DEFINITIONS;
export type StatusTone = (typeof STATUS_DEFINITIONS)[StatusKey]["tone"];
