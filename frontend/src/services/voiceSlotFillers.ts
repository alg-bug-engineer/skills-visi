import type { RunResponse } from '@/api/types'
import type { ActDef } from '@/composables/useTimeline'
import { summaryFor } from '@/composables/useTimeline'
import { voiceMethodFor } from '@/config/actDomainCopy'
import { productCopy } from '@/utils/productCopy'
import { downstreamConclusion } from '@/utils/downstream'

/** 仅诊断至归因幕播报本步结论（策略/配时/确认不追加）。 */
const VOICE_CONCLUSION_ACT_IDS = new Set([
  'act3_overflow',
  'act4_bottleneck',
  'act5_corridor',
  'act6_cause',
])

/** 仅播报步骤名 + 结论，省略目的与方法说明。 */
const VOICE_CONCLUSION_ONLY_ACT_IDS = new Set(['act4_bottleneck'])

export function voiceConclusionOnly(act: ActDef): boolean {
  return VOICE_CONCLUSION_ONLY_ACT_IDS.has(act.id)
}

/** 禁止 TTS 读出「核心结论」标签，并去掉冗余「结论：」前缀。 */
function sanitizeVoiceConclusion(text: string): string {
  return text.replace(/核心结论/g, '').replace(/^结论[：:]\s*/, '').trim()
}

/** 成因幕语音结论：仅播报主因短句，省略括号内补充说明。 */
function causePrimaryVoiceConclusion(resp: RunResponse | null): string {
  const cause = resp?.phases?.cause
  const ranked = cause?.cause_ranking?.find((item) => item.role?.includes('主'))?.cause
  const raw = ranked ?? cause?.cause_analysis?.primary_cause ?? ''
  const text = productCopy(raw)
  const short = text.split(/[（(]/)[0]?.trim() ?? text
  return short || '成因判断完成'
}

/** 下游承接幕：仅播报承接能力判别结论。 */
function bottleneckVoiceConclusion(resp: RunResponse | null): string {
  return productCopy(downstreamConclusion(resp?.phases?.diagnosis?.downstream_diagnosis))
}

function voiceConclusionFor(act: ActDef, resp: RunResponse | null): string {
  if (act.id === 'act6_cause') return causePrimaryVoiceConclusion(resp)
  if (act.id === 'act4_bottleneck') return bottleneckVoiceConclusion(resp)
  return sanitizeVoiceConclusion(summaryFor(act, resp))
}

/** 依据当前步骤填充语音方法槽位与结论槽位。 */
export function voiceSlotsForAct(act: ActDef, resp: RunResponse | null = null): Record<string, string> {
  const slots: Record<string, string> = {}
  if (!voiceConclusionOnly(act)) {
    const method = voiceMethodFor(act.id)
    if (method) slots.method = method
  }
  if (VOICE_CONCLUSION_ACT_IDS.has(act.id) && resp) {
    const conclusion = voiceConclusionFor(act, resp)
    if (conclusion) slots.conclusion = conclusion
  }
  return slots
}
