import { describe, expect, it, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'

describe('presentation store · 步骤间暂停', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('默认不暂停，waitForStepResume 立即 resolve', async () => {
    const s = usePresentationStore()
    await expect(s.waitForStepResume()).resolves.toBeUndefined()
  })

  it('暂停态下 waitForStepResume 阻塞直至 toggle 恢复', async () => {
    const s = usePresentationStore()
    s.stepPaused = true
    let done = false
    const pending = s.waitForStepResume().then(() => {
      done = true
    })
    await Promise.resolve()
    expect(done).toBe(false)
    s.toggleStepPause()
    await pending
    expect(done).toBe(true)
    expect(s.stepPaused).toBe(false)
  })

  it('pauseAwareSleep 在暂停期间不结束', async () => {
    vi.useFakeTimers()
    const s = usePresentationStore()
    s.stepPaused = true
    let done = false
    void s.pauseAwareSleep(500).then(() => {
      done = true
    })
    await vi.advanceTimersByTimeAsync(600)
    expect(done).toBe(false)
    s.toggleStepPause()
    await vi.advanceTimersByTimeAsync(100)
    expect(done).toBe(true)
    vi.useRealTimers()
  })

  it('reset 清除暂停态与 pending resume', async () => {
    const s = usePresentationStore()
    s.stepPaused = true
    void s.waitForStepResume()
    s.reset()
    expect(s.stepPaused).toBe(false)
  })

  it('暂停态下 resumeIfReady 不推进 waiting 幕，恢复后继续', () => {
    const s = usePresentationStore()
    s.mode = 'stream'
    s.applySnapshot({
      trace_id: 't',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: { intent: {}, diagnosis: {} } as never,
      plan: null,
      phase_results: [],
    })
    s.currentAct = 1
    s.waiting = true
    s.computingPhase = 'diagnosis'
    s.stepPaused = true
    s.resumeIfReady()
    expect(s.currentAct).toBe(1)
    s.toggleStepPause()
    expect(s.currentAct).toBe(2)
    expect(s.waiting).toBe(false)
  })

  it('tryAdvance 在暂停态下推迟推进，恢复后补执行', () => {
    const s = usePresentationStore()
    s.mode = 'batch'
    s.applySnapshot({
      trace_id: 't',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: { intent: {} } as never,
      plan: null,
      phase_results: [],
    })
    s.currentAct = 0
    s.stepPaused = true
    s.tryAdvance()
    expect(s.currentAct).toBe(0)
    expect(s.stepAdvancePending).toBe(true)
    s.toggleStepPause()
    expect(s.currentAct).toBe(1)
    expect(s.stepAdvancePending).toBe(false)
  })

  it('流式技能 error 在演示进行中不弹 toast，保持 running', () => {
    const s = usePresentationStore()
    s.status = 'running'
    s.currentAct = 3
    s.onStreamEvent({
      event: 'error',
      data: { phase: 'plan_generation', errors: ['所有候选方案未通过护栏校验'] },
    })
    expect(s.status).toBe('running')
    expect(s.toast).toBeNull()
    expect(s.errorMsg).toBeNull()
    expect(s.signal).not.toBe('error')
  })
})
