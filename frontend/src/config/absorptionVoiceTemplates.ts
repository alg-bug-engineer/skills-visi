/**
 * 经验吸收阶段固定语音文案（对齐 references/路口问题诊断以及固化技能 frontend-v2）。
 */

export const ABSORPTION_VOICE_GUIDE = {
  absorptionStart: '开始整理并写入本次诊断经验。',
  absorptionDone: '经验整理与技能写入完成。',
} as const

/** 吸收阶段 key → 播报文案；无配置的 stage 不播报。 */
export const ABSORPTION_STAGE_VOICE: Record<string, string> = {
  recap: '回顾本次诊断的关键约束与经验。',
  retrieve: '检索技能库，查找相似历史案例。',
  compare: '比对现有技能包，判断是否需要更新。',
  value: '提炼可复用的治理边界与诊断要点。',
  blueprint: '准备写入技能包文件。',
}
