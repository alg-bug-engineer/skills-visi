import type { ActDef } from '@/composables/useTimeline'
import type { VoiceCue } from '@/types/voice'

const ACT_ANNOUNCE: Record<string, string> = {
  act1_ticket: '诊断对象识别',
  act2_locate: '诊断对象定位',
  act3_overflow: '溢出证据核验',
  act4_bottleneck: '下游承接能力判别',
  act5_corridor: '上下游流向溯源',
  act6_cause: '成因归因与案例校验',
  act7_strategy: '治理策略与边界约束',
  act8_plan: '配时方案生成',
  act9_feedback: '方案确认与经验沉淀',
}

const spokenKeys = new Set<string>()

export function resetActVoiceKeys() {
  spokenKeys.clear()
}

export function voiceTextForAct(act: ActDef): string {
  return `${ACT_ANNOUNCE[act.id] ?? act.processTitle}。`
}

export function voiceCueForAct(act: ActDef | null, runKey: string): VoiceCue | null {
  if (!act) return null
  const key = `${runKey}:${act.id}`
  if (spokenKeys.has(key)) return null
  spokenKeys.add(key)
  return {
    id: `${key}:announce`,
    stepIndex: act.index,
    phase: act.id,
    kind: 'guide',
    text: voiceTextForAct(act),
    priority: act.index <= 1 ? 2 : 1,
  }
}
