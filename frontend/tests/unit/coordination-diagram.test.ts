import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CoordinationDiagram from '@/panels/CoordinationDiagram.vue'
import type { Coordination } from '@/api/types'

const available: Coordination = {
  available: true,
  direction: 'inbound',
  cycle_s: 120,
  source: 'link_geom+pg_signal+line_index',
  target: { inter_id: 'T', inter_name: '目标路口' },
  nodes: [
    {
      inter_id: 'U1',
      inter_name: '上游路口',
      role: 'upstream',
      spacing_m: 480,
      spacing_source: 'dim_link_info.length_m',
      offset_abs_s: 22,
      offset_source: 'plan_cfg.offset_sec',
      phase_diff_s: 12,
      travel_speed_kmh: 40,
      travel_time_s: 43.2,
      travel_source: 'line_index',
    },
    {
      inter_id: 'T',
      inter_name: '目标路口',
      role: 'target',
      spacing_m: 0,
      offset_abs_s: 10,
      phase_diff_s: 0,
      travel_speed_kmh: null,
      travel_time_s: null,
    },
  ],
}

describe('CoordinationDiagram', () => {
  it('renders real coordination fields when available', () => {
    const wrapper = mount(CoordinationDiagram, { props: { coordination: available } })
    const text = wrapper.get('[data-testid="coordination-diagram"]').text()
    expect(text).toContain('上游路口')
    expect(text).toContain('间距 480m')
    expect(text).toContain('相位差 +12s')
    expect(text).toContain('行程 43.2s')
    expect(text).toContain('40km/h')
    expect(text).not.toContain('暂不绘制协调图')
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('degrades with backend reason when unavailable', () => {
    const wrapper = mount(CoordinationDiagram, {
      props: { coordination: { available: false, reason: '缺少相邻路口绝对相位；缺少路段速度' } },
    })
    const text = wrapper.text()
    expect(text).toContain('暂不绘制协调图')
    expect(text).toContain('缺少相邻路口绝对相位')
    expect(wrapper.find('svg').exists()).toBe(false)
  })

  it('does not synthesize missing node fields', () => {
    const partial: Coordination = {
      available: true,
      direction: 'inbound',
      cycle_s: 120,
      nodes: [
        {
          inter_id: 'U1',
          inter_name: '上游路口',
          role: 'upstream',
          spacing_m: null,
          offset_abs_s: 22,
          phase_diff_s: 12,
          travel_speed_kmh: null,
          travel_time_s: null,
        },
        { inter_id: 'T', inter_name: '目标路口', role: 'target', spacing_m: 0, offset_abs_s: 10, phase_diff_s: 0, travel_speed_kmh: null, travel_time_s: null },
      ],
    }
    const text = mount(CoordinationDiagram, { props: { coordination: partial } }).text()
    expect(text).not.toContain('间距')
    expect(text).not.toContain('行程')
    expect(text).not.toContain('km/h')
    expect(text).toContain('相位差 +12s')
  })
})
