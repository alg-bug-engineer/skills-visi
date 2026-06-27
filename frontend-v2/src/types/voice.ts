/** Short voice cue for guided narration (not full screen text). */

export type VoiceCueKind = 'guide' | 'highlight' | 'transition'

export interface VoiceCue {
  id: string
  stepIndex: number
  phase: string
  kind: VoiceCueKind
  text: string
  priority: 0 | 1 | 2
}

export const ABSORPTION_STAGE_VOICE: Record<string, string> = {
  recap: '回顾本次诊断的关键约束与经验。',
  retrieve: '检索技能库，查找相似历史案例。',
  compare: '比对现有技能包，判断是否需要更新。',
  value: '提炼可复用的治理边界与诊断要点。',
  blueprint: '准备写入技能包文件。',
}
