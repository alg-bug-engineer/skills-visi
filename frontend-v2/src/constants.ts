/** 输入框默认示例，空内容时可直接点击发送 */
export const DEFAULT_PROMPT =
  '奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能溢出'

/** 治理建议二次确认：地图顶部引导条（区别于空格演示暂停） */
export const SUGGESTION_CONFIRM_BANNER =
  '问题诊断成立 · 回复「是」生成治理建议，或直接补充经验约束后发送'

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
/** 运行数据子步骤（traffic/direction/…）队列间隔 */
export const DATA_FETCH_STEP_PAUSE_MS = 350
/** 理解过程进入「运行数据」后，再延时揭示左侧运行数据与地图指标标注 */
export const RUNTIME_PRESENTATION_DELAY_MS = 1000

/** 饱和度 / 溢流风险 展示阈值（与 backend/rules/thresholds.yaml 对齐） */
export const THRESHOLDS = {
  saturationHigh: 0.8,
  spillbackRiskHigh: 0.8,
  imbalanceHigh: 0.3,
} as const
