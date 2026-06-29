import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { FlowTrace } from '../../types/evidence'
import FlowTraceMapSummary from './FlowTraceMapSummary.vue'

const TRACE: FlowTrace = {
  available: true,
  entry_traces: [
    {
      entry: '东进口',
      dir8_code: 2,
      narrative: '东进口约100辆过境车中，约82辆来自上一路口岔口，以直行为主（82辆）',
      vehicles_base: 100,
      upstream_movements: [],
    },
  ],
}

describe('FlowTraceMapSummary', () => {
  it('renders summary in map overlay when flow trace available', () => {
    const wrapper = mount(FlowTraceMapSummary, { props: { flowTrace: TRACE } })
    expect(wrapper.find('[data-testid="flow-trace-map-summary"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('上一跳来源')
    expect(wrapper.text()).toContain('100辆')
    expect(wrapper.text()).toContain('岔口')
  })

  it('hidden when unavailable', () => {
    const wrapper = mount(FlowTraceMapSummary, { props: { flowTrace: { available: false } } })
    expect(wrapper.find('[data-testid="flow-trace-map-summary"]').exists()).toBe(false)
  })
})
