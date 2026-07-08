import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PlanEvidencePanel from '@/panels/PlanEvidencePanel.vue'
import type { PlanCandidate } from '@/api/types'

function candidateWithEvidence(overTarget = false): PlanCandidate {
  return {
    plan_id: 'downstream_protection',
    name: '下游保护方案',
    status: 'valid',
    timing: {
      available: true,
      current_cycle_s: 130,
      cycle_s: 98,
      cycle_delta_s: -32,
      phase_stage_timing_list: [
        {
          phase_stage_id: '1',
          phase_stage_name: '西直、东直',
          green_time_s: 36,
          yellow_time_s: 3,
          all_red_time_s: 2,
          current_timing: { green_time_s: 60, yellow_time_s: 3, all_red_time_s: 2, stage_total_s: 65 },
          optimized_timing: { green_time_s: 36, yellow_time_s: 3, all_red_time_s: 2, stage_total_s: 41 },
          green_delta_s: -24,
          stage_delta_s: -24,
          movements: [{ movement_key: 'd6_t2', label: '西直', dir8No: 6, turnDirNo: 2, flow_available: true }],
          phase_saturation: 0.8746,
        },
      ],
      meta: {
        solver: 'scipy_slsqp_document_model',
        target_saturation: 0.75,
        max_phase_saturation: 0.8746,
        total_turn_flow_vph: 4078,
        direction_intensity_list: [
          { movementKey: 'd6_t2', label: '西直', intensity: overTarget ? 0.9 : 0.75 },
        ],
        notes: ['使用文档 SQP 模型'],
        data_quality: { current_timing_source: 'pg_signal_plan' },
      },
    },
  }
}

describe('PlanEvidencePanel', () => {
  it('renders cycle comparison, stage cards, intensity and audit evidence', () => {
    const wrapper = mount(PlanEvidencePanel, {
      props: { candidate: candidateWithEvidence() },
    })

    expect(wrapper.text()).toContain('优化对比')
    expect(wrapper.text()).toContain('130s')
    expect(wrapper.text()).toContain('98')
    expect(wrapper.text()).toContain('阶段 1')
    expect(wrapper.text()).toContain('西直')
    expect(wrapper.text()).toContain('各方向供需强度')
    expect(wrapper.text()).toContain('75.0%')
    expect(wrapper.text()).toContain('求解器')
    expect(wrapper.text()).toContain('scipy_slsqp_document_model')
  })

  it('falls back when backend evidence is incomplete', () => {
    const wrapper = mount(PlanEvidencePanel, {
      props: {
        candidate: {
          plan_id: 'downstream_protection',
          name: '下游保护方案',
          status: 'valid',
          timing: {
            available: false,
            cycle_s: 98,
            reason: '方案证据字段不完整，无法生产级展示',
            missing_fields: ['timing.current_cycle_s'],
            phase_stage_timing_list: [],
          },
        } as PlanCandidate,
      },
    })

    expect(wrapper.text()).toContain('后端未返回可审计方案证据')
    expect(wrapper.text()).toContain('timing.current_cycle_s')
  })

  it('marks intensity over target as risk', () => {
    const wrapper = mount(PlanEvidencePanel, {
      props: { candidate: candidateWithEvidence(true) },
    })

    expect(wrapper.find('[data-testid="intensity-row-risk"]').exists()).toBe(true)
  })
})
