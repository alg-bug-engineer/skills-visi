import type { RunResponse } from '@/api/types'
import type { ActDef } from '@/composables/useTimeline'
import { composeVoiceAnnounce, VOICE_TEMPLATES } from '@/config/voiceTemplates'
import { voiceConclusionOnly, voiceSlotsForAct, voiceTitleOnly } from '@/services/voiceSlotFillers'
import { voiceSpatialCognition } from '@/services/voiceSpatialCognition'
import type { VoiceCue } from '@/types/voice'

const spokenKeys = new Set<string>()

export function resetActVoiceKeys() {
  spokenKeys.clear()
}

export function voiceTextForAct(act: ActDef, resp: RunResponse | null): string {
  const def = VOICE_TEMPLATES[act.id]
  if (!def) return `${act.processTitle}。`
  // 步骤名以右侧处置闭环 processTitle 为准，避免模板与流程改名后漂移。
  const aligned = { ...def, stepTitle: act.processTitle }
  const slots = voiceSlotsForAct(act, resp)
  let text = composeVoiceAnnounce(aligned, slots, {
    conclusionOnly: voiceConclusionOnly(act),
    titleOnly: voiceTitleOnly(act),
  })
  if (act.id === 'act2_locate') {
    const cognition = voiceSpatialCognition(resp)
    if (cognition) text = `${cognition}。${text}`
  }
  return text
}

/** 构建语音 cue（不占用去重位，供预合成使用）。 */
export function buildVoiceCue(act: ActDef | null, runKey: string, resp: RunResponse | null): VoiceCue | null {
  if (!act) return null
  // 方案确认与经验沉淀：不播报，避免与人工决策界面抢注意力。
  if (act.id === 'act10_feedback') return null
  if (!VOICE_TEMPLATES[act.id]) return null
  const key = `${runKey}:${act.id}`
  return {
    id: `${key}:announce`,
    stepIndex: act.index,
    phase: act.id,
    kind: 'guide',
    text: voiceTextForAct(act, resp),
    priority: act.index <= 1 ? 2 : 1,
  }
}

/** 进入某步骤时触发播报：固定目的文案 + 动态槽位结论。 */
export function voiceCueForAct(
  act: ActDef | null,
  runKey: string,
  resp: RunResponse | null,
): VoiceCue | null {
  if (!act) return null
  if (act.id === 'act10_feedback') return null
  const key = `${runKey}:${act.id}`
  if (spokenKeys.has(key)) return null
  spokenKeys.add(key)
  return buildVoiceCue(act, runKey, resp)
}
