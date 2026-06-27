export type AbsorptionStage =
  | 'idle'
  | 'recap'
  | 'decompose'
  | 'retrieve'
  | 'compare'
  | 'value'
  | 'blueprint'
  | 'done'

export type AbsorptionAction = 'CREATE' | 'UPDATE' | 'UNCHANGED' | null

export type EvidenceChip = {
  key: string
  label: string
  value: string
}

export type ValueRow = {
  key: string
  label: string
  before: string
  after: string
}

export type ValueSnapshot = {
  what: { title: string; bullets: string[] }
  why_rows: ValueRow[]
  delta_rows: string[]
}

export type AbsorptionTraceLine = {
  seq: number
  stage: AbsorptionStage
  kind: 'monologue' | 'stage_marker' | 'evidence'
  text?: string
  chips?: EvidenceChip[]
  status: 'running' | 'done'
  durationMs?: number
}

export type ExperienceAbsorptionState = {
  active: boolean
  currentStage: AbsorptionStage
  lines: AbsorptionTraceLine[]
  valueSnapshot: ValueSnapshot | null
  action: AbsorptionAction
  progress: number
  skillId: string
  intersection: string
}

export type SkillAbsorptionEvent = {
  event: 'skill_absorption'
  type: string
  stage: string
  timestamp: string
  payload: Record<string, unknown>
}

export const ABSORPTION_STAGES: Array<{ key: AbsorptionStage; label: string }> = [
  { key: 'recap', label: '回顾' },
  { key: 'decompose', label: '解构' },
  { key: 'retrieve', label: '检索' },
  { key: 'compare', label: '比对' },
  { key: 'value', label: '价值' },
  { key: 'blueprint', label: '转化' },
]

export function createInitialAbsorptionState(): ExperienceAbsorptionState {
  return {
    active: false,
    currentStage: 'idle',
    lines: [],
    valueSnapshot: null,
    action: null,
    progress: 0,
    skillId: '',
    intersection: '',
  }
}
