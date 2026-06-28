import type { SkillAbsorptionEvent } from '../types/skillAbsorption'
import type { SkillBuildEvent } from '../types/skillBuild'

export type SkillBufferedEvent =
  | { domain: 'absorption'; event: SkillAbsorptionEvent }
  | { domain: 'build'; event: SkillBuildEvent }

/** 需逐字/逐块流式呈现 — 必须同步应用，不可进 AnalysisQueue */
export const ABSORPTION_STREAM_EVENTS = new Set([
  'thought_delta',
  'evidence',
  'stage_running',
])

export const SKILL_BUILD_STREAM_EVENTS = new Set([
  'thought_delta',
  'file_delta',
  'file_diff',
  'model_call_start',
  'model_call_done',
])

export function isSkillAbsorptionStreamEvent(eventType: string): boolean {
  return ABSORPTION_STREAM_EVENTS.has(eventType)
}

export function isSkillBuildStreamEvent(eventType: string): boolean {
  return SKILL_BUILD_STREAM_EVENTS.has(eventType)
}

export function isSkillStreamBufferedEvent(item: SkillBufferedEvent): boolean {
  if (item.domain === 'absorption') {
    return isSkillAbsorptionStreamEvent(item.event.type)
  }
  return isSkillBuildStreamEvent(item.event.type)
}

/** 阶段结束后入队 pause gate（与地图子步骤边界对齐；不在 start 上 settle 以免阻塞流式事件） */
export function shouldEnqueueAbsorptionPauseGate(eventType: string): boolean {
  return eventType === 'stage_done'
}

export function shouldEnqueueSkillBuildPauseGate(eventType: string): boolean {
  return eventType === 'stage_done' || eventType === 'file_done'
}

export function frameYield(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()))
}
