import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import CauseCard from '@/cards/CauseCard.vue'
import ProblemVerificationCard from '@/cards/ProblemVerificationCard.vue'
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
              structured_tags: {
                场景层级: ['干线协调'],
                策略动作: ['绿波协调', '防溢流保护'],
              },
            },
          ],
        },
      },
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

function snapDiagnosis(diagnosis: Record<string, unknown>): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: { diagnosis } as unknown as RunResponse['phases'],
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
    expect(wrapper.text()).toContain('晚高峰干线瓶颈')

    await wrapper.find('[data-testid="case-summary-row"]').trigger('click')

    expect(wrapper.find('[data-testid="case-detail"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-help"]').text()).toContain('下游约束')
    expect(wrapper.find('[data-testid="case-dimensions"]').text()).toContain('下游承接')
    expect(wrapper.find('[data-testid="case-transferable"]').text()).toContain('协调配时')
    expect(wrapper.find('[data-testid="case-caveats"]').text()).toContain('配时结构')
    expect(wrapper.find('[data-testid="case-structured-tags"]').text()).toContain('干线协调')
    expect(wrapper.find('[data-testid="case-structured-tags"]').text()).toContain('绿波协调')
  })
})

describe('ProblemVerificationCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders 常发性/周期性 + 派生 marker + 配时/运行状态', () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snapDiagnosis({
        metrics: { saturation: 1.8, los: 'F' },
        problem_regularity: {
          recurring: '晚高峰该方向饱和度持续偏高',
          periodic: '周三同时段历史规律显示压力偏高',
          basis: '基于同时段饱和度与周内规律派生，非实测统计',
        },
        timing_profile: { cycle_s: 206, time_plan_count: 33, plan_name: null },
        overflow_verification: { verified: true, risk_level: 'high', message: '排队接近进口道边界' },
      }),
    )
    const text = mount(ProblemVerificationCard).text()
    expect(text).toContain('常发性')
    expect(text).toContain('晚高峰该方向饱和度持续偏高')
    expect(text).toContain('周期性')
    expect(text).toContain('派生')
    expect(text).toContain('206')
    expect(text).toContain('1.8')
  })

  it('renders nothing when diagnosis rich fields all absent', () => {
    const s = usePresentationStore()
    s.applySnapshot(snapDiagnosis({}))
    const wrapper = mount(ProblemVerificationCard)
    expect(wrapper.find('[data-testid="insight-card"]').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })
})
