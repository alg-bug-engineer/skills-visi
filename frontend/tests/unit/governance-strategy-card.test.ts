import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import GovernanceStrategyCard from '@/cards/GovernanceStrategyCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function snap(strategy: Record<string, unknown>): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      strategy,
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

describe('GovernanceStrategyCard', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('renders principles + 参考依据 chips (行业/路口)', () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snap({
        strategy: {
          principles: ['单点放行调整纳入干线联控约束'],
          recommended: ['目标方向小步放行'],
          hard_constraints: ['行人过街时间不低于最小值'],
        },
        reference_basis: {
          industry_scene: '一般路口优化',
          intersection_case_ids: ['011wwe28ctu00001'],
        },
      }),
    )
    const wrapper = mount(GovernanceStrategyCard)
    const text = wrapper.text()
    expect(text).toContain('单点放行调整纳入干线联控约束')
    const chips = wrapper.findAll('[data-testid="ref-chip"]')
    expect(chips.length).toBe(2)
    expect(text).toContain('行业·一般路口优化')
    expect(text).toContain('路口·011wwe28ctu00001')
  })

  it('emits open-case-library event with correct detail on chip click', async () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snap({
        strategy: { principles: ['P'] },
        reference_basis: { industry_scene: '一般路口优化', intersection_case_ids: ['011wwe28ctu00001'] },
      }),
    )
    const events: CustomEvent[] = []
    const handler = (e: Event) => events.push(e as CustomEvent)
    window.addEventListener('open-case-library', handler as EventListener)

    const wrapper = mount(GovernanceStrategyCard)
    const chips = wrapper.findAll('[data-testid="ref-chip"]')
    await chips[0].trigger('click') // industry
    await chips[1].trigger('click') // intersection

    window.removeEventListener('open-case-library', handler as EventListener)

    expect(events.length).toBe(2)
    expect(events[0].detail.tab).toBe('industry')
    expect(events[0].detail.refId).toBe('industry-scene-general_intersection')
    expect(events[0].detail.sceneId).toBe('general_intersection')
    expect(events[1].detail.tab).toBe('intersection')
    expect(events[1].detail.refId).toBe('inter-case-011wwe28ctu00001')
  })

  it('renders nothing when strategy absent', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap({}))
    const wrapper = mount(GovernanceStrategyCard)
    expect(wrapper.find('[data-testid="insight-card"]').exists()).toBe(false)
  })
})
