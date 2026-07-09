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
})
