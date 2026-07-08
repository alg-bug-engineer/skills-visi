import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DiagnosisTicketCard from '@/cards/DiagnosisTicketCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

const RAW_INPUT = '文化西路与舜华路交叉口东向西直行晚高峰排队溢出，帮我看看'

function snap(): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: {
      object_type: 'intersection',
      intersection_name: '文化西路与舜华路交叉口',
      inter_id: 'INT_001',
      lng: 117.11,
      lat: 36.65,
      time_range: '18:10-18:30',
      period: 'evening_peak',
      direction: 'east_to_west',
      movement: 'straight',
      problem_type: 'queue_spillover',
      constraints: ['avoid_downstream_spillover'],
      diagnosis_scope: 'corridor',
      governance_goal: 'mitigate_spillover',
      match_confidence: 0.96,
      match_method: 'explicit',
    },
    phases: {},
    plan: null,
    phase_results: [],
  } as unknown as RunResponse
}

describe('DiagnosisTicketCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders a ul list (not a dl) with li items', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap())
    s.userInput = RAW_INPUT
    const wrapper = mount(DiagnosisTicketCard)
    expect(wrapper.find('ul.nlu-list').exists()).toBe(true)
    expect(wrapper.find('dl').exists()).toBe(false)
    expect(wrapper.findAll('ul.nlu-list li').length).toBeGreaterThan(0)
  })

  it('shows the raw user question text', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap())
    s.userInput = RAW_INPUT
    const text = mount(DiagnosisTicketCard).text()
    expect(text).toContain('原始问题')
    expect(text).toContain(RAW_INPUT)
  })

  it('shows the 诊断范围 field', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap())
    s.userInput = RAW_INPUT
    const text = mount(DiagnosisTicketCard).text()
    expect(text).toContain('诊断范围')
    expect(text).toContain('目标路口 + 上下游 + 干线协调')
  })
})
