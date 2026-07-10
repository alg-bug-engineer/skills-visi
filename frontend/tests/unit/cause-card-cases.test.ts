import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import CauseCard from '@/cards/CauseCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function snapWithStructuredCases(): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      cause: {
        cause_ranking: [{ rank: 1, role: '主因', cause: '下游承接不足' }],
        cause_scores: { 下游承接不足: 0.9 },
        case_cards: {
          matched_count: 12,
          high_similarity_count: 3,
          cards: [
            {
              case_id: 'A',
              title: '晚高峰干线瓶颈',
              similarity_dimensions: [
                { key: 'problem', label: '问题形态：排队溢出' },
                { key: 'downstream', label: '空间：下游承接' },
              ],
              transferable_actions: ['上下游协调配时', '防溢流相位保护'],
              caveats: ['需核对本路口配时结构'],
              help_summary: '提示下游约束与防溢流做法',
              similarity_tier: 'high',
            },
          ],
        },
      },
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

describe('CauseCard · 结构化相似案例', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('展开代表案例可见相似维度、帮助与分级', async () => {
    const s = usePresentationStore()
    s.applySnapshot(snapWithStructuredCases())

    const wrapper = mount(CauseCard)
    expect(wrapper.text()).toContain('命中 12')
    expect(wrapper.text()).toContain('高相似 3')

    await wrapper.find('[data-testid="case-id-chip"]').trigger('click')

    expect(wrapper.find('[data-testid="case-detail"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-help"]').text()).toContain('下游约束')
    expect(wrapper.find('[data-testid="case-dimensions"]').text()).toContain('下游承接')
    expect(wrapper.find('[data-testid="case-transferable"]').text()).toContain('协调配时')
    expect(wrapper.find('[data-testid="case-caveats"]').text()).toContain('配时结构')
  })
})
