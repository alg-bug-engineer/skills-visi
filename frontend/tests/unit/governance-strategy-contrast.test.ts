import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import GovernanceStrategyCard from '@/cards/GovernanceStrategyCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function snapWithContrast(): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      strategy: {
        strategy: { principles: ['防溢流优先'], hard_constraints: [] },
        experience_contrast: {
          available: true,
          items: [
            {
              dimension: '策略选择',
              without_experience: { summary: '仅依赖实时指标评分 → 下游保护方案' },
              with_experience: {
                summary: '小步释放方案（参考 1 条经验/案例）',
                refs: [{ type: 'user_experience', record_id: 'ue_1', label: '需分析下游' }],
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

describe('GovernanceStrategyCard · 经验对照', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('展示 experience_contrast 对照行', () => {
    const s = usePresentationStore()
    s.applySnapshot(snapWithContrast())
    const wrapper = mount(GovernanceStrategyCard)
    expect(wrapper.find('[data-testid="strategy-experience-contrast"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('无经验')
    expect(wrapper.text()).toContain('小步释放方案')
  })
})
