/**
 * Skill 复用 vs 沉淀 — UI/语音回归策略（REGRESSION_TEST_SPEC §1、§14）
 */

/** 不应展示「技能固化」理解步骤或 absorption 语音的 skill_action */
export const SKILL_ACTIONS_WITHOUT_SOLIDIFICATION_UI = [
  'reused_no_persist',
  'skipped_no_user_suggestion',
  'declined',
  'declined_create',
  'declined_update',
] as const

export type SkillActionWithoutSolidificationUi =
  (typeof SKILL_ACTIONS_WITHOUT_SOLIDIFICATION_UI)[number]

/** 治理建议已生成、无需技能固化：分析结束，输入锁定并展示返回主页 */
export const SKILL_ACTIONS_ANALYSIS_TERMINAL = [
  'reused_no_persist',
  'skipped_no_user_suggestion',
] as const

export type SkillActionAnalysisTerminal = (typeof SKILL_ACTIONS_ANALYSIS_TERMINAL)[number]

export function shouldEnterAnalysisTerminal(
  skillAction: string | undefined,
  state: string,
): boolean {
  if (state !== 'done' || !skillAction) return false
  return (SKILL_ACTIONS_ANALYSIS_TERMINAL as readonly string[]).includes(skillAction)
}

/** 是否应在理解过程面板展示步骤 7（技能固化） */
export function shouldShowSkillSolidificationStep(
  skillAction: string | undefined,
  state: string,
): boolean {
  if (!skillAction) return false
  if (
    (SKILL_ACTIONS_WITHOUT_SOLIDIFICATION_UI as readonly string[]).includes(skillAction)
  ) {
    return false
  }
  if (state === 'awaiting_confirm' && skillAction === 'awaiting_create') {
    return true
  }
  return skillAction === 'created' || skillAction === 'updated'
}

/** 经验吸收 SSE 是否应触发语音播报 */
export function shouldEnqueueAbsorptionVoice(eventType: string): boolean {
  return (
    eventType === 'skill_absorption_start' ||
    eventType === 'stage_start' ||
    eventType === 'skill_absorption_done'
  )
}

/** skill_build SSE 是否应触发语音播报 */
export function shouldEnqueueSkillBuildVoice(eventType: string): boolean {
  return eventType === 'skill_build_start' || eventType === 'skill_build_done'
}

/** 空格暂停是否应视为「演示进行中」（含经验吸收与技能固化） */
export function isSkillPresentationActive(
  absorptionActive: boolean,
  skillBuildVisible: boolean,
  skillBuildStatus: string,
): boolean {
  if (absorptionActive) return true
  return skillBuildVisible && skillBuildStatus === 'running'
}
