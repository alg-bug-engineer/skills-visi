import { afterEach, describe, expect, it, vi } from 'vitest'
import { useExperienceAbsorption } from '@/composables/useExperienceAbsorption'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

describe('useExperienceAbsorption (instant)', () => {
  it('consumes all 6 stages and reaches terminal state synchronously', () => {
    const { state, start } = useExperienceAbsorption()
    start(result.absorption, { instant: true })

    expect(state.lines).toHaveLength(6)
    expect(state.currentStage).toBe('done')
    expect(state.progress).toBe(100)
    expect(state.action).toBe('CREATE')
    expect(state.valueSnapshot).not.toBeNull()
    expect(state.valueSnapshot?.why_rows).toHaveLength(3)
    // 每行携带独白与至少一个证据 chip
    expect(state.lines[0].monologue.length).toBeGreaterThan(0)
    expect(state.lines[0].chips.length).toBeGreaterThan(0)
  })

  it('invokes onDone once terminal', () => {
    const onDone = vi.fn()
    const { start } = useExperienceAbsorption()
    start(result.absorption, { instant: true, onDone })
    expect(onDone).toHaveBeenCalledTimes(1)
  })
})

describe('useExperienceAbsorption (timed driver)', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('progresses through stages over time and finishes', () => {
    vi.useFakeTimers()
    const onDone = vi.fn()
    const { state, start } = useExperienceAbsorption()
    start(result.absorption, { instant: false, onDone })

    // 起始未完成
    expect(state.currentStage).not.toBe('done')

    vi.advanceTimersByTime(200)
    expect(state.lines.length).toBeGreaterThan(0)
    expect(state.progress).toBeGreaterThan(0)

    // 推进到全部阶段 + finalize（6 阶段各上限 700ms）
    vi.advanceTimersByTime(10_000)
    expect(state.currentStage).toBe('done')
    expect(state.progress).toBe(100)
    expect(state.lines).toHaveLength(6)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('reset cancels pending timers (advancing after reset is inert)', () => {
    vi.useFakeTimers()
    const { state, start, reset } = useExperienceAbsorption()
    start(result.absorption, { instant: false })

    vi.advanceTimersByTime(300)
    reset()

    expect(state.currentStage).toBe('idle')
    expect(state.lines).toHaveLength(0)

    vi.advanceTimersByTime(10_000)
    expect(state.currentStage).toBe('idle')
    expect(state.lines).toHaveLength(0)
    expect(state.progress).toBe(0)
  })
})
