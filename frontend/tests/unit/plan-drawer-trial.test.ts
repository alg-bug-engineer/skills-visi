import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import PlanDrawer from '@/panels/PlanDrawer.vue'
import { usePresentationStore } from '@/stores/presentation'
import fixture from '@/mock/cases/case_a_demo_fixture.json'
import type { RunResponse } from '@/api/types'

describe('PlanDrawer · 可控试运行闭环', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('将 Case A 显示为可下发试运行，而不是不可执行的观察方案', () => {
    const store = usePresentationStore()
    store.applySnapshot(fixture as unknown as RunResponse)

    const wrapper = mount(PlanDrawer, {
      global: {
        stubs: {
          PlanEvidencePanel: { template: '<div data-testid="plan-evidence-stub" />' },
          CoordinationDiagram: { template: '<div />' },
        },
      },
    })

    const primary = wrapper.get('.btn--primary')
    expect(primary.attributes('disabled')).toBeUndefined()
    expect(primary.text()).toContain('下发并试运行 5 周期')
    expect(wrapper.text()).toContain('为什么这样调')
    expect(wrapper.text()).toContain('下发后的试运行闭环')
    expect(wrapper.text()).not.toContain('不可直接执行')
    expect(wrapper.text()).not.toContain('门控前')
    expect(wrapper.text()).not.toContain('门控后')
    expect(wrapper.text()).not.toContain('信号周期不得超过 180s')
    expect(wrapper.text()).not.toContain('单相位绿灯不得超过 60s')
  })

  it('同一 plan_id 优先采用后端 recommended 最终证据快照', () => {
    const response = structuredClone(fixture) as unknown as RunResponse
    const candidate = response.plan?.candidates?.[0]
    if (candidate) candidate.timing = undefined

    const store = usePresentationStore()
    store.applySnapshot(response)
    const wrapper = mount(PlanDrawer, {
      global: {
        stubs: {
          PlanEvidencePanel: { template: '<div data-testid="plan-evidence-stub" />' },
          CoordinationDiagram: { template: '<div />' },
        },
      },
    })

    expect(wrapper.find('[data-testid="plan-evidence-stub"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('需要后端补齐配时明细')
  })
})
