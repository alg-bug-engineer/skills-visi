import { computed, ref } from 'vue'
import { STEP_INDICES } from '../constants'
import type { PipelinePhase } from '../types/presentation'

export interface PresentationLayerGates {
  insightStack: boolean
  evidenceNote: boolean
  hudBar: boolean
  timingRingAuto: boolean
  corridorWaveAuto: boolean
}

const HUD_PHASES: PipelinePhase[] = [
  'direction',
  'saturation',
  'imbalance',
  'evidence',
  'rule',
  'conclusion',
]

/**
 * 控制地图 overlay 组件揭示时序（功能全保留，仅错峰展示）。
 * 不对用户暴露「演示模式」；由 pipeline phase 与理解步骤 index 驱动。
 */
export function usePresentationSequence() {
  const focusStepIndex = ref(-1)
  const pipelinePhase = ref<PipelinePhase>('idle')

  function syncFromStepIndex(index: number) {
    if (index >= 0) {
      focusStepIndex.value = Math.max(focusStepIndex.value, index)
    }
  }

  function syncFromPhase(phase: PipelinePhase) {
    pipelinePhase.value = phase
  }

  function reset() {
    focusStepIndex.value = -1
    pipelinePhase.value = 'idle'
  }

  const allowInsightStack = computed(() => focusStepIndex.value >= STEP_INDICES.PROBLEM_EVIDENCE)

  const allowEvidenceNote = computed(() => focusStepIndex.value >= STEP_INDICES.PROBLEM_EVIDENCE)

  const allowHudBar = computed(() => {
    const step = focusStepIndex.value
    const phase = pipelinePhase.value
    if (step < STEP_INDICES.DATA_FETCH) return false
    if (step === STEP_INDICES.COGNITION) return false
    if (step === STEP_INDICES.DATA_FETCH) {
      return HUD_PHASES.includes(phase)
    }
    return step >= STEP_INDICES.PROBLEM_EVIDENCE
  })

  const allowTimingRingAuto = computed(() => focusStepIndex.value >= STEP_INDICES.RULE)

  const allowCorridorWaveAuto = computed(() => focusStepIndex.value >= STEP_INDICES.RULE)

  const layers = computed<PresentationLayerGates>(() => ({
    insightStack: allowInsightStack.value,
    evidenceNote: allowEvidenceNote.value,
    hudBar: allowHudBar.value,
    timingRingAuto: allowTimingRingAuto.value,
    corridorWaveAuto: allowCorridorWaveAuto.value,
  }))

  return {
    focusStepIndex,
    pipelinePhase,
    layers,
    syncFromStepIndex,
    syncFromPhase,
    reset,
    allowInsightStack,
    allowEvidenceNote,
    allowHudBar,
    allowTimingRingAuto,
    allowCorridorWaveAuto,
  }
}
