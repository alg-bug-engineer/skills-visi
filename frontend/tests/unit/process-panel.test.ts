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

  it('步骤暂停不打断当前幕打字，仅在幕末阻塞切入下一幕', async () => {
    Object.defineProperty(navigator, 'webdriver', { value: false, configurable: true })
    vi.useFakeTimers()
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = true
    store.currentAct = 0
    store.setVoiceBarrier(() => Promise.resolve())

    mount(ProcessPanel)
    await flushPromises()

    store.stepPaused = true
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()
    expect(store.currentAct).toBe(0)

    store.toggleStepPause()
    await vi.advanceTimersByTimeAsync(12_000)
    await flushPromises()
    expect(store.currentAct).toBeGreaterThan(0)
    vi.useRealTimers()
    Object.defineProperty(navigator, 'webdriver', { value: true, configurable: true })
  })
})

describe('ProcessPanel · 旁白缓存一致性', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('已完成幕展开时显示冻结旁白全文（多行），与打字内容一致', async () => {
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = false
    store.currentAct = 0

    const wrapper = mount(ProcessPanel)
    await flushPromises()

    store.currentAct = 1
    await flushPromises()

    const frozen = wrapper.findAll('[data-testid="process-narration-frozen"]')
    expect(frozen.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('正在解析')
  })

  it('完成过的幕持续显示明细与证据卡，不自动折叠成单行', async () => {
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = false
    store.currentAct = 0
    const wrapper = mount(ProcessPanel)
    await flushPromises()

    store.currentAct = 1
    await flushPromises()
    store.currentAct = 2
    await flushPromises()

    expect(wrapper.find('[data-act-index="0"]').classes()).not.toContain('collapsed')
    expect(wrapper.text()).toContain('正在解析')
    expect(wrapper.findComponent({ name: 'DiagnosisTicketCard' }).isVisible()).toBe(true)
  })
})
