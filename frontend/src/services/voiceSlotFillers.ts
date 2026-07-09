import type { RunResponse } from '@/api/types'
import type { ActDef } from '@/composables/useTimeline'
import { summaryFor } from '@/composables/useTimeline'
import { voiceMethodFor } from '@/config/actDomainCopy'

/** 诊断幕（act3）及之后播报本步结论，与 summaryFor 对齐。 */
const VOICE_CONCLUSION_FROM_INDEX = 2

/** 禁止 TTS 读出「核心结论」标签，并去掉冗余「结论：」前缀。 */
function sanitizeVoiceConclusion(text: string): string {
  return text.replace(/核心结论/g, '').replace(/^结论[：:]\s*/, '').trim()
}

/** 依据当前步骤填充语音方法槽位与结论槽位。 */
export function voiceSlotsForAct(act: ActDef, resp: RunResponse | null = null): Record<string, string> {
  const slots: Record<string, string> = {}
  const method = voiceMethodFor(act.id)
  if (method) slots.method = method
  if (act.index >= VOICE_CONCLUSION_FROM_INDEX && resp) {
    const conclusion = sanitizeVoiceConclusion(summaryFor(act, resp))
    if (conclusion) slots.conclusion = conclusion
  }
  return slots
}
