import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// 桩 submitDecision 以覆盖 accept() 改动路径；其余端点保留原实现。
const submitDecision = vi.fn()
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>()
  return { ...actual, submitDecision: (...args: unknown[]) => submitDecision(...args) }
})

import { usePresentationStore } from '@/stores/presentation'

describe('presentation store · accept() 进入固化确认', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    submitDecision.mockReset()
  })
  afterEach(() => vi.clearAllMocks())

  it('下发成功后进入 prompt，不 reset，保留 response 与 planId', async () => {
    submitDecision.mockResolvedValue({ ok: true, recorded: true })
    const s = usePresentationStore()
    s.traceId = 't1'
    s.response = { trace_id: 't1' } as never

    await s.accept('downstream_protection')

    expect(s.solidifyPhase).toBe('prompt')
    expect(s.pendingSolidifyPlanId).toBe('downstream_protection')
    expect(s.response).not.toBeNull()
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
