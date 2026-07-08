import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

// 仅桩 solidifySkill，返回真实 fixture；其余端点保留原实现（store 依赖它们）。
vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>()
  return {
    ...actual,
    solidifySkill: vi.fn(async () => result),
  }
})

import SkillSolidifyOverlay from '@/panels/SkillSolidifyOverlay.vue'
import { usePresentationStore } from '@/stores/presentation'

// 强制即时动画路径（生产代码路径不变）：overlay/composables 探测 navigator.webdriver。
let originalWebdriver: PropertyDescriptor | undefined
beforeAll(() => {
  originalWebdriver = Object.getOwnPropertyDescriptor(navigator, 'webdriver')
  Object.defineProperty(navigator, 'webdriver', { value: true, configurable: true })
})
afterAll(() => {
  if (originalWebdriver) Object.defineProperty(navigator, 'webdriver', originalWebdriver)
})

describe('SkillSolidifyOverlay flow', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders prompt and returns home on decline', async () => {
    const store = usePresentationStore()
    store.traceId = 't1'
    store.solidifyPhase = 'prompt'

    const wrapper = mount(SkillSolidifyOverlay, { global: { stubs: { teleport: true } } })
    await flushPromises()

    expect(wrapper.find('[data-testid="solidify-prompt"]').exists()).toBe(true)

    await wrapper.find('[data-testid="solidify-decline"]').trigger('click')
    await flushPromises()

    expect(store.solidifyPhase).toBe('idle')
    expect(store.dock).toBe('input')
  })

  it('confirm drives absorbing→building→completed and finish returns home', async () => {
    const store = usePresentationStore()
    store.traceId = 't1'
    store.pendingSolidifyPlanId = 'downstream_protection'
    store.solidifyPhase = 'prompt'

    const wrapper = mount(SkillSolidifyOverlay, { global: { stubs: { teleport: true } } })
    await flushPromises()

    await wrapper.find('[data-testid="solidify-confirm"]').trigger('click')
    // solidifySkill (mock) resolves → skillResult set → instant chain runs synchronously
    await flushPromises()
    await flushPromises()

    expect(store.solidifyPhase).toBe('completed')

    const finish = wrapper.find('[data-testid="solidify-finish"]')
    expect(finish.exists()).toBe(true)

    await finish.trigger('click')
    await flushPromises()

    expect(store.solidifyPhase).toBe('idle')
    expect(store.dock).toBe('input')
  })
})
