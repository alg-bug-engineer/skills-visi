import type { PhaseStageTiming, PlanCandidate, PlanTimingEvidence } from '@/api/types'

export type TrialTiming = PlanTimingEvidence & {
  available?: boolean | null
  label?: string
  reason?: string | null
}

/** 只对已经可执行的候选读取拟实施配时；核验方案始终展示现状基线。 */
export function trialTimingOf(candidate: PlanCandidate | null | undefined): TrialTiming | null {
  if (!candidate) return null
  const proposed = (candidate as PlanCandidate & { proposed_timing?: TrialTiming }).proposed_timing
  const canUseProposed =
    candidate.plan_id !== 'verification_plan' &&
    candidate.executable === true &&
    candidate.plan_status === 'trial_ready'
  if (canUseProposed && proposed?.available !== false && proposed?.phase_stage_timing_list?.length) {
    return proposed
  }
  return candidate.timing ?? null
}

/** 配时主证据只由周期与逐阶段现状/建议秒数决定；释放方向、强度是独立审计维度。 */
export function hasCoreTimingEvidence(timing: PlanTimingEvidence | null | undefined): boolean {
  if (!timing || timing.current_cycle_s == null || timing.cycle_s == null) return false
  const stages = timing.phase_stage_timing_list ?? []
  return stages.some((stage) => {
    const before = stage.current_timing?.green_time_s
    const after = stage.optimized_timing?.green_time_s ?? stage.green_time_s
    return typeof before === 'number' && Number.isFinite(before)
      && typeof after === 'number' && Number.isFinite(after)
  })
}

export function isLegacyVerificationPlan(candidate: PlanCandidate | null | undefined): boolean {
  return Boolean(
    candidate?.plan_id === 'verification_plan' || candidate?.timing?.verification_baseline,
  )
}

export function actualCycleDelta(timing: PlanTimingEvidence | null | undefined): number | null {
  if (!timing) return null
  if (typeof timing.current_cycle_s === 'number' && typeof timing.cycle_s === 'number') {
    return timing.cycle_s - timing.current_cycle_s
  }
  return typeof timing.cycle_delta_s === 'number' ? timing.cycle_delta_s : null
}

function numericDelta(stage: PhaseStageTiming): number {
  if (typeof stage.green_delta_s === 'number') return stage.green_delta_s
  const before = stage.current_timing?.green_time_s
  const after = stage.optimized_timing?.green_time_s ?? stage.green_time_s
  return typeof before === 'number' && typeof after === 'number' ? after - before : 0
}

export function changedStages(timing: PlanTimingEvidence | null | undefined): PhaseStageTiming[] {
  return (timing?.phase_stage_timing_list ?? []).filter((stage) => numericDelta(stage) !== 0)
}

export function formatDelta(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value === 0 ? '不变' : `${value > 0 ? '+' : ''}${value}s`
}

/** 从真正展示的阶段秒数生成动作，避免与 action_package 中的旧摘要互相矛盾。 */
export function timingActionLines(candidate: PlanCandidate | null | undefined): string[] {
  const timing = trialTimingOf(candidate)
  if (!timing) return []
  const lines = changedStages(timing).map((stage) => {
    const before = stage.current_timing?.green_time_s
    const after = stage.optimized_timing?.green_time_s ?? stage.green_time_s
    const values =
      typeof before === 'number' && typeof after === 'number'
        ? `${before}s → ${after}s（${formatDelta(after - before)}）`
        : formatDelta(numericDelta(stage))
    return `${stage.phase_stage_name || `阶段 ${stage.phase_stage_id}`}：绿灯 ${values}`
  })
  const current = timing.current_cycle_s
  const next = timing.cycle_s
  if (typeof current === 'number' && typeof next === 'number') {
    lines.push(`信号周期：${current}s → ${next}s（${formatDelta(next - current)}）`)
  }
  return lines
}

export function compactTimingSummary(candidate: PlanCandidate | null | undefined): string {
  const timing = trialTimingOf(candidate)
  if (!timing) return ''
  const stages = changedStages(timing)
  const target = stages.find((stage) => stage.role === 'target') ?? stages.find((stage) => numericDelta(stage) > 0)
  const donor = stages.find((stage) => stage.role === 'donor') ?? stages.find((stage) => numericDelta(stage) < 0)
  const parts: string[] = []
  if (target) parts.push(`${target.phase_stage_name} ${formatDelta(numericDelta(target))}`)
  if (donor) parts.push(`${donor.phase_stage_name} ${formatDelta(numericDelta(donor))}`)
  const cycle = actualCycleDelta(timing)
  if (cycle != null) parts.push(`周期${formatDelta(cycle)}`)
  return parts.join('，')
}
