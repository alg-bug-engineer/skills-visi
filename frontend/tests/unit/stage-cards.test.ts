import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StageCards from '@/viz/StageCards.vue'
import type { PhaseStageTiming } from '@/api/types'

const stages: PhaseStageTiming[] = [
  {
    phase_stage_id: '1',
    phase_stage_name: '西直、东左',
    green_time_s: 36,
    yellow_time_s: 3,
    all_red_time_s: 2,
    min_green_time_s: 14,
    max_green_time_s: 90,
    phase_saturation: 0.8746,
    current_timing: { green_time_s: 60, yellow_time_s: 3, all_red_time_s: 2, stage_total_s: 65 },
    optimized_timing: { green_time_s: 36, yellow_time_s: 3, all_red_time_s: 2, stage_total_s: 41 },
    green_delta_s: -24,
    stage_delta_s: -24,
    movements: [
      { movement_key: 'd6_t0', label: '西直', dir8No: 6, turnDirNo: 0, turnFlowTotal: 960, laneCount: 2, saturation: 0.87 },
      { movement_key: 'd2_t1', label: '东左', dir8No: 2, turnDirNo: 1, turnFlowTotal: 420, laneCount: 1, saturation: 0.76 },
    ],
  },
]

describe('StageCards', () => {
  it('renders reference-style timing evidence and passes whole stage to canvas', () => {
    const wrapper = mount(StageCards, {
      props: { stages },
      global: {
        stubs: {
          StageMovementCanvas: {
            props: ['stage'],
            template: '<div data-testid="stage-canvas-stub">{{ stage.phase_stage_name }}</div>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('西直、东左')
    expect(wrapper.text()).toContain('65s')
    expect(wrapper.text()).toContain('41s')
    expect(wrapper.text()).toContain('-24s')
    expect(wrapper.text()).toContain('最小/最大绿 14s / 90s')
    expect(wrapper.text()).toContain('饱和度 87.5%')
    expect(wrapper.get('[data-testid="stage-canvas-stub"]').text()).toBe('西直、东左')
  })
})
