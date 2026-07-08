import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ProblemVerificationCard from '@/cards/ProblemVerificationCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function snap(diagnosis: Record<string, unknown>): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      diagnosis,
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

describe('ProblemVerificationCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders 常发性/周期性 + 派生 marker + 配时/运行状态', () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snap({
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
    // 诚实标注：派生
    expect(text).toContain('派生')
    // 配时周期
    expect(text).toContain('206')
    // 运行状态：饱和度
    expect(text).toContain('1.8')
  })

  it('renders nothing when diagnosis rich fields all absent', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap({}))
    const wrapper = mount(ProblemVerificationCard)
    expect(wrapper.find('[data-testid="insight-card"]').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })
})
