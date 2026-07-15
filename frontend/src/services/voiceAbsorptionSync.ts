import { ABSORPTION_VOICE_GUIDE } from '@/config/voiceTemplates'
import type { SkillSolidificationResult } from '@/api/types'
import type { VoiceCue } from '@/types/voice'
import { productCopy } from '@/utils/productCopy'

const SOLIDIFY_STEP_INDEX = 9
const spokenAbsorptionKeys = new Set<string>()

export function resetAbsorptionVoiceKeys() {
  spokenAbsorptionKeys.clear()
}

function buildCue(runKey: string, phase: string, text: string, kind: VoiceCue['kind']): VoiceCue {
  return {
    id: `${runKey}:absorption:${phase}`,
    stepIndex: SOLIDIFY_STEP_INDEX,
    phase: `absorption:${phase}`,
    kind,
    text,
    priority: 0,
  }
}

export function voiceCueForAbsorptionStart(runKey: string): VoiceCue | null {
  const phase = 'start'
  const key = `${runKey}:${phase}`
  if (spokenAbsorptionKeys.has(key)) return null
  spokenAbsorptionKeys.add(key)
  return buildCue(runKey, phase, ABSORPTION_VOICE_GUIDE.absorptionStart, 'transition')
}

function absorptionResultSummary(result: SkillSolidificationResult): string {
  const snapshot = result.absorption.value_snapshot
  const absorbed = (snapshot.what?.bullets ?? [])
    .map((item) => productCopy(String(item)))
    .filter(Boolean)
    .slice(0, 4)
  const reuse = (snapshot.why_rows ?? [])
    .map((row) => productCopy(row.after))
    .filter(Boolean)
    .slice(0, 2)
  const action = result.action === 'updated'
    ? '更新到当前技能包'
    : result.action === 'unchanged'
      ? '与现有技能规则核对后保留'
      : '写入当前技能包'
  const what = absorbed.length ? absorbed.join('、') : '诊断结论、适用范围与安全约束'
  const how = reuse.length ? reuse.join('，并') : '按路口、时段和问题类型自动检索复用'
  return `本次吸收了${what}。已将诊断结论、适用范围和安全约束结构化${action}，后续可${how}。`
}

export function voiceCueForAbsorptionDone(
  runKey: string,
  result: SkillSolidificationResult,
): VoiceCue | null {
  const phase = 'done'
  const key = `${runKey}:${phase}`
  if (spokenAbsorptionKeys.has(key)) return null
  spokenAbsorptionKeys.add(key)
  return buildCue(runKey, phase, absorptionResultSummary(result), 'transition')
}
