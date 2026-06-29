import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FlowTimingGovernanceCard from './FlowTimingGovernanceCard.vue'
import type { FlowTimingGovernance, PrimaryDiagnosis } from '../../types/evidence'

function makeGovernance(overrides: Partial<FlowTimingGovernance> = {}): FlowTimingGovernance {
  return {
    match_verdict: 'mismatch',
    match_narrative: '高流量转向的有效绿灯占比偏低',
    summary: '头牌结论；同步扫描命中：饱和度',
    problems: [],
    expert_rules: [],
    ...overrides,
  }
}

const primaryTimingOptimizable: PrimaryDiagnosis = {
  type: 'timing_optimizable',
  headline: '东直行已过饱和（0.95），而北左转绿灯仍有富余——属于绿灯分配不均，配时可改善',
  lever: '建议把北左转的部分绿灯时间让给东直行，优先调整绿信比分配',
  severity: 'high',
  evidence: ['最高转向饱和度 0.95', '转向饱和度极差 0.42'],
  structure_limited: false,
}

describe('FlowTimingGovernanceCard', () => {
  it('renders the primary diagnosis headline, lever and severity color', () => {
    const wrapper = mount(FlowTimingGovernanceCard, {
      props: { governance: makeGovernance({ primary_diagnosis: primaryTimingOptimizable }) },
    })
    const primary = wrapper.find('.primary')
    expect(primary.exists()).toBe(true)
    expect(primary.classes()).toContain('sev-high')
    expect(wrapper.find('.primary-headline').text()).toContain('分配不均')
    expect(wrapper.find('.primary-lever').text()).toContain('绿信比')
    const evidence = wrapper.findAll('.primary-evidence li').map((li) => li.text())
    expect(evidence).toContain('最高转向饱和度 0.95')
  })

  it('falls back to summary only when no primary diagnosis is present', () => {
    const wrapper = mount(FlowTimingGovernanceCard, {
      props: { governance: makeGovernance() },
    })
    expect(wrapper.find('.primary').exists()).toBe(false)
    expect(wrapper.find('.summary').exists()).toBe(true)
  })

  it('hides the summary line once a primary diagnosis is shown', () => {
    const wrapper = mount(FlowTimingGovernanceCard, {
      props: { governance: makeGovernance({ primary_diagnosis: primaryTimingOptimizable }) },
    })
    expect(wrapper.find('.summary').exists()).toBe(false)
  })

  it('does not render the match line when sample is insufficient (no placeholder)', () => {
    const wrapper = mount(FlowTimingGovernanceCard, {
      props: {
        governance: makeGovernance({
          match_verdict: 'insufficient',
          match_narrative: '转向流量或配时样本不足，暂无法评价流量-绿信比一致性',
          primary_diagnosis: primaryTimingOptimizable,
        }),
      },
    })
    expect(wrapper.find('.match-line').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无法评价')
  })

  it('omits the expert block when there are no expert rules', () => {
    const wrapper = mount(FlowTimingGovernanceCard, {
      props: { governance: makeGovernance({ primary_diagnosis: primaryTimingOptimizable }) },
    })
    expect(wrapper.find('.expert').exists()).toBe(false)
  })
})
