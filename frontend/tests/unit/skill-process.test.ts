import { afterEach, describe, expect, it, vi } from 'vitest'
import { useExperienceAbsorption } from '@/composables/useExperienceAbsorption'
import { useSkillBuildProcess, type SkillBuildMeta } from '@/composables/useSkillBuildProcess'
import type { SkillBuildFileNode } from '@/types/skillBuild'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

function metaFrom(r: SkillSolidificationResult): SkillBuildMeta {
  return {
    skillId: r.skill_id,
    skillDir: r.skill_dir,
    downloadUrl: r.download_url,
    intersection: r.intersection ?? '',
    timePeriodLabel: r.time_period_label ?? '',
    action: r.action,
  }
}

function flatten(nodes: SkillBuildFileNode[]): SkillBuildFileNode[] {
  return nodes.flatMap((n) => [n, ...(n.children ? flatten(n.children) : [])])
}

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
  afterEach(() => vi.useRealTimers())

  it('progresses through stages over time and finishes', () => {
    vi.useFakeTimers()
    const onDone = vi.fn()
    const { state, start } = useExperienceAbsorption()
    start(result.absorption, { instant: false, onDone })

    expect(state.currentStage).not.toBe('done')

    vi.advanceTimersByTime(200)
    expect(state.lines.length).toBeGreaterThan(0)
    expect(state.progress).toBeGreaterThan(0)

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

describe('useSkillBuildProcess (instant)', () => {
  it('reaches completed state with full file tree and contents', () => {
    const { state, start } = useSkillBuildProcess()
    start(result.build, metaFrom(result), { instant: true })

    expect(state.status).toBe('completed')
    expect(state.progress).toBe(100)
    expect(state.downloadUrl).toBe(result.download_url)
    expect(state.skillId).toBe(result.skill_id)

    const flat = flatten(state.files)
    const paths = flat.map((n) => n.path)
    expect(paths).toContain('SKILL.md')
    expect(paths).toContain('reference.md')
    expect(paths).toContain('skill.meta.json')
    const scriptsDir = flat.find((n) => n.path === 'scripts')
    expect(scriptsDir?.type).toBe('directory')
    expect(paths).toContain('scripts/fetch_traffic_data.sql')

    expect(state.fileContents['SKILL.md']?.length ?? 0).toBeGreaterThan(0)
    expect(state.fileContents['scripts/fetch_traffic_data.sql']?.length ?? 0).toBeGreaterThan(0)
    expect(state.stages).toHaveLength(result.build.stages.length)
    expect(state.stages.every((s) => s.status === 'done')).toBe(true)
  })
})

describe('useSkillBuildProcess (timed driver)', () => {
  afterEach(() => vi.useRealTimers())

  it('progresses through stages/files over time and finishes', () => {
    vi.useFakeTimers()
    const onDone = vi.fn()
    const { state, start } = useSkillBuildProcess()
    start(result.build, metaFrom(result), { instant: false, onDone })

    expect(state.status).toBe('running')
    expect(state.currentStage).not.toBe('completed')

    vi.advanceTimersByTime(50)
    expect(state.progress).toBeGreaterThan(0)

    vi.advanceTimersByTime(60_000)
    expect(state.status).toBe('completed')
    expect(state.progress).toBe(100)
    expect(state.fileContents['SKILL.md']).toBe(
      result.build.files.find((f) => f.path === 'SKILL.md')?.content,
    )
    expect(state.downloadUrl).toBe(result.download_url)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('reset cancels pending timers (advancing after reset is inert)', () => {
    vi.useFakeTimers()
    const { state, start, reset } = useSkillBuildProcess()
    start(result.build, metaFrom(result), { instant: false })

    vi.advanceTimersByTime(50)
    reset()

    expect(state.status).toBe('idle')
    expect(state.files).toHaveLength(0)

    vi.advanceTimersByTime(60_000)
    expect(state.status).toBe('idle')
    expect(state.files).toHaveLength(0)
    expect(state.progress).toBe(0)
  })
})
