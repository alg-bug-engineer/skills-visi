/**
 * 经验吸收（技能固化前置）前端类型契约。
 * 契约以真实后端 `SkillSolidificationResult.absorption` 为准（见 mock/skill_solidify_fixture.json）。
 * 仅借鉴 references/frontend-v2，未 import 参考代码；本项目后端返回一次性结构化结果（非 SSE 流）。
 */

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

/** 证据 chip：value 可为字符串或数字（真实响应两种都出现）。 */
export type EvidenceChip = {
  key: string
  label: string
  value: string | number
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

/** 吸收终端 trace 行：一阶段一行，含独白与证据 chips。 */
export type AbsorptionTraceLine = {
  seq: number
  stage: AbsorptionStage
  label: string
  monologue: string
  chips: EvidenceChip[]
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
