import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const submitDecision = vi.fn()
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>()
  return { ...actual, submitDecision: (...args: unknown[]) => submitDecision(...args) }
})

const result = fixture as unknown as SkillSolidificationResult

describe('presentation store · 固化状态机', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('reset() clears solidifyPhase / skillResult / pendingSolidifyPlanId', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'building'
    s.skillResult = result
    s.pendingSolidifyPlanId = 'downstream_protection'

    s.reset()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.pendingSolidifyPlanId).toBeNull()
    expect(s.dock).toBe('input')
  })

  it('declineSolidify() returns to input dock and idle phase', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'prompt'
    s.dock = 'plan'
    s.skillResult = result

    s.declineSolidify()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.dock).toBe('input')
    expect(s.toast).toContain('已返回主页')
  })

  it('finishSolidify() returns to input dock and idle phase', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'completed'
    s.dock = 'plan'
    s.skillResult = result

    s.finishSolidify()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.dock).toBe('input')
    expect(s.toast).toContain('已固化并入库')
  })

  it('setSolidifyPhase() advances the phase', () => {
    const s = usePresentationStore()
    s.setSolidifyPhase('building')
    expect(s.solidifyPhase).toBe('building')
  })
})

describe('presentation store · accept() 进入固化确认', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    submitDecision.mockReset()
  })
  afterEach(() => vi.clearAllMocks())

  it('下发成功后隐藏方案抽屉并进入 prompt，不 reset，保留 response 与 planId', async () => {
    submitDecision.mockResolvedValue({ ok: true, recorded: true })
    const s = usePresentationStore()
    s.traceId = 't1'
    s.response = { trace_id: 't1' } as never
    s.dock = 'plan'

    await s.accept('downstream_protection')

    expect(s.solidifyPhase).toBe('prompt')
    expect(s.pendingSolidifyPlanId).toBe('downstream_protection')
    expect(s.response).not.toBeNull()
    expect(s.dock).toBe('running')
  })

  it('下发失败则提示并返回主页，不进入固化', async () => {
    submitDecision.mockResolvedValue({ ok: false, reason: '网络错误' })
    const s = usePresentationStore()
    s.traceId = 't1'
    s.response = { trace_id: 't1' } as never

    await s.accept('downstream_protection')

    expect(s.solidifyPhase).toBe('idle')
    expect(s.dock).toBe('input')
    expect(s.toast).toContain('下发失败')
  })

  it('无 traceId 时 accept 直接返回不动作', async () => {
    const s = usePresentationStore()
    s.traceId = null

    await s.accept('p1')

    expect(submitDecision).not.toHaveBeenCalled()
    expect(s.solidifyPhase).toBe('idle')
  })
})
