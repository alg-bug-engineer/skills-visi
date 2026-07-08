import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import UnderstandingPanel from '@/panels/UnderstandingPanel.vue'
import { usePresentationStore } from '@/stores/presentation'
import expertKnowledge from '@/data/expertKnowledge.json'
import type { RunResponse } from '@/api/types'

/** 构造仅含成因阶段（含相似案例卡）的快照，用于点亮「路口案例」。 */
function snapWithCases(): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      intent: {},
      cause: {
        case_cards: {
          cards: [
            {
              case_id: 'CASE_777',
              title: '文化路溢出治理',
              similarity: 0.91,
              action: '双向绿波 + 上游调控',
              outcome: '排队下降 40%',
              lesson: '优先消散下游',
            },
          ],
        },
      },
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

describe('UnderstandingPanel · 案例库（行业/路口）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('行业案例子标签渲染全部 19 个场景条目', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-industry"]').trigger('click')

    const scenes = wrapper.findAll('[data-testid="industry-scene"]')
    expect(scenes.length).toBe((expertKnowledge as unknown[]).length)
    expect(scenes.length).toBe(19)
  })

  it('搜索框过滤场景列表（匹配数少于全部）', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-industry"]').trigger('click')

    const input = wrapper.find('[data-testid="industry-search"]')
    await input.setValue('货运通道')

    const scenes = wrapper.findAll('[data-testid="industry-scene"]')
    expect(scenes.length).toBeGreaterThanOrEqual(1)
    expect(scenes.length).toBeLessThan(19)
    expect(wrapper.text()).toContain('货运通道关键节点')
  })

  it('路口案例子标签渲染已有案例并展示 case_id', async () => {
    const s = usePresentationStore()
    s.applySnapshot(snapWithCases())

    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')

    const items = wrapper.findAll('[data-testid="inter-case"]')
    expect(items.length).toBe(1)
    const text = wrapper.text()
    expect(text).toContain('文化路溢出治理')
    expect(text).toContain('CASE_777')
    expect(wrapper.find('#inter-case-CASE_777').exists()).toBe(true)
  })

  it('路口案例在成因阶段未就绪时显示等待提示', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')

    expect(wrapper.findAll('[data-testid="inter-case"]').length).toBe(0)
    expect(wrapper.text()).toContain('待检索')
  })
})
