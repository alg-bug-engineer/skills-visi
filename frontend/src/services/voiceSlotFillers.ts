import type { ActDef } from '@/composables/useTimeline'
import { voiceMethodFor } from '@/config/actDomainCopy'

/** 依据当前步骤填充语音方法槽位（不含结论）。 */
export function voiceSlotsForAct(act: ActDef): Record<string, string> {
  const method = voiceMethodFor(act.id)
  return method ? { method } : {}
}
