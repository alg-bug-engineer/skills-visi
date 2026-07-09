import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import { usePresentationStore } from '@/stores/presentation'
import fixture from '@/mock/run_1_fixture.json'
import type { RunResponse } from '@/api/types'

const fx = fixture as unknown as RunResponse

let originalWebdriver: PropertyDescriptor | undefined
beforeAll(() => {
  originalWebdriver = Object.getOwnPropertyDescriptor(navigator, 'webdriver')
  Object.defineProperty(navigator, 'webdriver', { value: true, configurable: true })
})
afterAll(() => {
  if (originalWebdriver) Object.defineProperty(navigator, 'webdriver', originalWebdriver)
})

describe('ProcessPanel · autoPlay act 推进', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('语音 barrier 不阻塞时自动推进到下一幕', async () => {
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = true
    store.currentAct = 0
    store.setVoiceBarrier(() => Promise.resolve())

    mount(ProcessPanel)
    await flushPromises()
    await vi.waitFor(() => expect(store.currentAct).toBeGreaterThan(0), { timeout: 3000 })
  })

  it('语音 barrier 永久挂起时不应阻塞幕推进', async () => {
    vi.useFakeTimers()
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = true
    store.currentAct = 0
    store.setVoiceBarrier(() => new Promise(() => {}))

    mount(ProcessPanel)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(12_001)
    await flushPromises()
    expect(store.currentAct).toBeGreaterThan(0)
    vi.useRealTimers()
  })
})
