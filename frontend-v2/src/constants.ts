/** 输入框默认示例，空内容时可直接点击发送 */
export const DEFAULT_PROMPT =
  '奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能溢出'

/** 分析流水线步骤标签（含 0625 问题验证） */
export const ANALYSIS_STEP_LABELS = [
  '理解描述',
  '锁定路口',
  '路口结构',
  '运行数据',
  '问题印证',
  '原因诊断',
  '治理建议',
  '经验固化',
] as const

export const STEP_INDICES = {
  UNDERSTAND: 0,
  INTERSECTION: 1,
  COGNITION: 2,
  DATA_FETCH: 3,
  PROBLEM_EVIDENCE: 4,
  RULE: 5,
  SUGGESTION: 6,
  SKILL: 7,
} as const

export const STEP_PAUSE_MS = 2200

/** 饱和度 / 溢流风险 展示阈值（与 backend/rules/thresholds.yaml 对齐） */
export const THRESHOLDS = {
  saturationHigh: 0.8,
  spillbackRiskHigh: 0.8,
  imbalanceHigh: 0.3,
} as const
