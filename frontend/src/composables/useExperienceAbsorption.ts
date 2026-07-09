import { reactive } from 'vue'
import type { SkillSolidificationResult } from '@/api/types'
import {
  createInitialAbsorptionState,
  type AbsorptionStage,
  type ExperienceAbsorptionState,
} from '@/types/skillAbsorption'

type Absorption = SkillSolidificationResult['absorption']

export interface AbsorptionRunOptions {
  /** 即时全量（不排 timer）。默认自动探测 reduced-motion / webdriver。 */
  instant?: boolean
  /** 每阶段等待上限（毫秒），真实 duration_ms 被裁剪到该值。 */
  maxStageDelayMs?: number
  /** 可选：路口 / 技能 id（absorption 载荷不含，交由调用方透传）。 */
  skillId?: string
  intersection?: string
  onStageStart?: (stageKey: string) => void
  onStart?: () => void
  onDone?: () => void
}

/** 探测是否应即时完成（无障碍偏好或自动化环境）。 */
function detectInstant(): boolean {
  const reduced =
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const automation =
    typeof navigator !== 'undefined' && (navigator as Navigator).webdriver === true
  return reduced || automation
}

/**
 * 经验吸收驱动：消费后端一次性 `absorption` 结构，按阶段推进 trace + 价值表。
 * 纯 Vue 响应式 + timer，无 DOM 依赖；timer 可在 reset() 全部取消，避免测试串扰。
 */
export function useExperienceAbsorption() {
  const state = reactive<ExperienceAbsorptionState>(createInitialAbsorptionState())
  const timers: number[] = []

  function clearTimers() {
    for (const id of timers) clearTimeout(id)
    timers.length = 0
  }

  function schedule(fn: () => void, ms: number) {
    const id = window.setTimeout(fn, ms)
    timers.push(id)
  }

  function reset() {
    clearTimers()
    Object.assign(state, createInitialAbsorptionState())
  }

  function applyStage(stage: Absorption['stages'][number], index: number, total: number) {
    const key = stage.key as AbsorptionStage
    state.currentStage = key
    state.lines.push({
      seq: state.lines.length + 1,
      stage: key,
      label: stage.label,
      monologue: stage.monologue,
      chips: stage.evidence_chips ?? [],
      status: 'done',
      durationMs: stage.duration_ms,
    })
    state.progress = Math.min(95, Math.round(((index + 1) / total) * 100))
  }

  function finalize(absorption: Absorption) {
    state.currentStage = 'done'
    state.progress = 100
    state.valueSnapshot = absorption.value_snapshot
    state.action = absorption.action
    state.active = false
  }

  function start(absorption: Absorption, opts: AbsorptionRunOptions = {}) {
    reset()
    const instant = opts.instant ?? detectInstant()
    const cap = opts.maxStageDelayMs ?? 700
    const stages = absorption.stages ?? []
    const total = Math.max(stages.length, 1)

    state.active = true
    state.action = absorption.action
    if (opts.skillId) state.skillId = opts.skillId
    if (opts.intersection) state.intersection = opts.intersection
    opts.onStart?.()

    if (instant) {
      stages.forEach((stage, i) => {
        opts.onStageStart?.(stage.key)
        applyStage(stage, i, total)
      })
      finalize(absorption)
      opts.onDone?.()
      return
    }

    let acc = 0
    stages.forEach((stage, i) => {
      schedule(() => {
        opts.onStageStart?.(stage.key)
        applyStage(stage, i, total)
      }, acc)
      acc += Math.min(Math.max(stage.duration_ms ?? 400, 0), cap)
    })
    schedule(() => {
      finalize(absorption)
      opts.onDone?.()
    }, acc)
  }

  return { state, start, reset }
}
