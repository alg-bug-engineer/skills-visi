import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

vi.mock('@/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints')>()
  return {
    ...actual,
    solidifySkill: vi.fn(async () => result),
  }
})

import SkillSolidifyOverlay from '@/panels/SkillSolidifyOverlay.vue'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import { usePresentationStore } from '@/stores/presentation'

let originalWebdriver: PropertyDescriptor | undefined
beforeAll(() => {
  originalWebdriver = Object.getOwnPropertyDescriptor(navigator, 'webdriver')
  Object.defineProperty(navigator, 'webdriver', { value: true, configurable: true })
})
afterAll(() => {
  if (originalWebdriver) Object.defineProperty(navigator, 'webdriver', originalWebdriver)
})

describe('Skill solidify flow', () => {
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

  it('confirm drives absorbing→building→completed in ProcessPanel tab and finish returns home', async () => {
    const store = usePresentationStore()
    store.traceId = 't1'
    store.pendingSolidifyPlanId = 'downstream_protection'
    store.solidifyPhase = 'prompt'
    store.status = 'running'
    store.currentAct = 8

    const overlay = mount(SkillSolidifyOverlay, { global: { stubs: { teleport: true } } })
    const panel = mount(ProcessPanel)
    await flushPromises()

    await overlay.find('[data-testid="solidify-confirm"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(store.solidifyPhase).toBe('completed')
    expect(panel.find('[data-testid="process-solidify-tab"]').exists()).toBe(true)

    const finish = panel.find('[data-testid="solidify-finish"]')
    expect(finish.exists()).toBe(true)

    await finish.trigger('click')
    await flushPromises()

    expect(store.solidifyPhase).toBe('idle')
    expect(store.dock).toBe('input')
  })
})
