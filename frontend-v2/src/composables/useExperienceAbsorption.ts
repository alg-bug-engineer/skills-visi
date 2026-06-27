import { reactive, ref } from 'vue'
import {
  type AbsorptionStage,
  type AbsorptionTraceLine,
  type EvidenceChip,
  type ExperienceAbsorptionState,
  type SkillAbsorptionEvent,
  type ValueSnapshot,
  createInitialAbsorptionState,
} from '../types/skillAbsorption'

function parseValueSnapshot(payload: Record<string, unknown>): ValueSnapshot | null {
  const what = payload.what as ValueSnapshot['what'] | undefined
  const whyRows = payload.why_rows as ValueSnapshot['why_rows'] | undefined
  if (!what || !whyRows) return null
  return {
    what,
    why_rows: whyRows,
    delta_rows: Array.isArray(payload.delta_rows)
      ? (payload.delta_rows as string[])
      : [],
  }
}

function upsertRunningLine(
  lines: AbsorptionTraceLine[],
  seq: number,
  stage: AbsorptionStage,
  kind: AbsorptionTraceLine['kind'],
): AbsorptionTraceLine {
  const existing = lines.find((line) => line.stage === stage && line.status === 'running' && line.kind === kind)
  if (existing) return existing
  const line: AbsorptionTraceLine = { seq, stage, kind, status: 'running' }
  lines.push(line)
  return line
}

export function reduceAbsorptionEvent(
  state: ExperienceAbsorptionState,
  event: SkillAbsorptionEvent,
  seq: number,
): void {
  const payload = event.payload
  const stage = (event.stage || state.currentStage) as AbsorptionStage

  switch (event.type) {
    case 'skill_absorption_start':
      state.active = true
      state.currentStage = 'recap'
      state.progress = 1
      state.skillId = String(payload.skill_id ?? '')
      state.intersection = String(payload.intersection ?? '')
      state.action = (payload.action as ExperienceAbsorptionState['action']) ?? null
      break
    case 'stage_start':
      state.currentStage = stage
      if (stage === 'value') {
        const snapshot = parseValueSnapshot(payload)
        if (snapshot) state.valueSnapshot = snapshot
      }
      upsertRunningLine(state.lines, seq, stage, 'stage_marker')
      break
    case 'thought_delta': {
      const delta = String(payload.delta ?? '')
      if (!delta) break
      const line = upsertRunningLine(state.lines, seq, stage, 'monologue')
      line.text = `${line.text ?? ''}${delta}`
      break
    }
    case 'evidence': {
      const chip = payload.chip as EvidenceChip | undefined
      const chips = payload.chips as EvidenceChip[] | undefined
      const line = upsertRunningLine(state.lines, seq, stage, 'evidence')
      if (chip) {
        line.chips = line.chips ?? []
        if (!line.chips.some((item) => item.key === chip.key)) {
          line.chips.push(chip)
        }
      } else if (chips?.length) {
        line.chips = chips
      }
      if (stage === 'compare' && Array.isArray(payload.changes)) {
        line.text = (payload.changes as string[]).map((c) => `diff：${c}`).join('\n')
      }
      break
    }
    case 'stage_done': {
      for (const line of state.lines) {
        if (line.stage === stage && line.status === 'running') {
          line.status = 'done'
          if (payload.duration_ms != null) {
            line.durationMs = Number(payload.duration_ms)
          }
        }
      }
      if (stage === 'value' && payload.library_count_after != null) {
        state.progress = 85
      }
      break
    }
    case 'skill_absorption_done':
      state.currentStage = 'done'
      state.progress = 100
      state.action = (payload.action as ExperienceAbsorptionState['action']) ?? state.action
      for (const line of state.lines) {
        if (line.status === 'running') line.status = 'done'
      }
      break
    default:
      break
  }
}

export function useExperienceAbsorption() {
  const state = reactive<ExperienceAbsorptionState>(createInitialAbsorptionState())
  const eventSeq = ref(0)

  function reset() {
    Object.assign(state, createInitialAbsorptionState())
    eventSeq.value = 0
  }

  function applyEvent(event: SkillAbsorptionEvent) {
    eventSeq.value += 1
    reduceAbsorptionEvent(state, event, eventSeq.value)
  }

  return {
    state,
    reset,
    applyEvent,
  }
}
