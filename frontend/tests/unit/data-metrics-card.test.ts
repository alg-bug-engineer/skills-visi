import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DataMetricsCard from '@/cards/DataMetricsCard.vue'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function baseMetrics() {
  return {
    queue_length_m: 158,
    storage_length_m: 883.94,
    queue_ratio: 0.1787,
    saturation: 0.0305,
    green_utilization: 0.5741,
    stop_count: 0.59,
    avg_delay_s: 41.04,
    time_series_trend: 'pg_loaded',
  }
}

function snap(metrics: Record<string, unknown>): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: {
      object_type: 'intersection',
      intersection_name: '经十路与转山西路路口',
      inter_id: '011wwe289qc00001',
      lng: 117.1,
      lat: 36.65,
      time_range: '18:10-18:30',
      period: 'evening_peak',
      direction: 'east_to_west',
      movement: 'through',
      problem_type: 'queue_spillover',
      constraints: [],
      diagnosis_scope: 'corridor',
      governance_goal: 'mitigate_spillover',
      match_confidence: 0.9,
      match_method: 'explicit',
    },
    phases: {
      diagnosis: {
        metrics,
        overflow_verification: {
          verified: true,
          risk_level: 'high',
          message: '东向西直行排队接近进口道空间边界',
        },
        data_source: 'pg',
      },
    },
    plan: null,
    phase_results: [],
  } as unknown as RunResponse
}

describe('DataMetricsCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders the detailed 运行数据 panel with per-approach / per-movement / imbalance / los', () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snap({
        ...baseMetrics(),
        los: 'F',
        by_approach: [
          { approach: '东进口', saturation: 3.49, delay_index: 1.8, los: 'F' },
          { approach: '西进口', saturation: 1.78, delay_index: 1.42, los: 'F' },
          { approach: '北进口', saturation: 1.51, delay_index: 1.31, los: 'E' },
        ],
        by_movement: [
          { movement: '东左转', saturation: 1.77, green_utilization: 1.77, level: '过饱和' },
          { movement: '东直行', saturation: 0.93, green_utilization: 0.93, level: '偏高' },
        ],
        imbalance_index: 0.46,
        approach_count: 4,
        lane_count: 26,
      }),
    )
    const wrapper = mount(DataMetricsCard)
    const text = wrapper.text()
    // 卡片内不再重复标题「运行数据」（面板头已提供），仅渲染明细
    expect(wrapper.find('[data-testid="metrics-detail"]').exists()).toBe(true)
    // per-approach 三行无序列表：饱和度 / 延误指数 / 服务水平
    expect(text).toContain('东进口')
    expect(text).toContain('饱和度')
    expect(text).toContain('延误指数')
    expect(text).toContain('3.49')
    // per-movement + level tag
    expect(text).toContain('东左转')
    expect(text).toContain('过饱和')
    // 方向失衡
    expect(text).toContain('方向失衡')
    expect(text).toContain('0.46')
    // 服务水平 / F
    expect(text).toContain('服务水平')
    expect(text).toContain('F')
    // must NOT show green_utilization as a bogus percentage like 177%
    expect(text).not.toContain('177')
  })

  it('falls back to the hero 排队比 + grid when rich fields are absent', () => {
    const s = usePresentationStore()
    s.applySnapshot(snap(baseMetrics()))
    const wrapper = mount(DataMetricsCard)
    const text = wrapper.text()
    expect(text).toContain('排队比')
    expect(text).toContain('绿灯利用率')
    // hero number rendered from queue_ratio
    expect(text).toContain('0.18')
    // no per-approach rows
    expect(text).not.toContain('东进口')
  })

  it('renders saturation_rate when saturation alias is absent', () => {
    const store = usePresentationStore()
    store.response = {
      trace_id: 't',
      completed: true,
      pipeline_complete: true,
      diagnosis_ticket: null,
      phases: {
        diagnosis: {
          metrics: {
            queue_ratio: 0.2,
            queue_length_m: 40,
            storage_length_m: 200,
            saturation_rate: 0.88,
            green_utilization: 0.57,
            stop_count: 1.2,
            avg_delay_s: 35,
            time_series_trend: 'pg_loaded',
          },
        },
      },
      plan: null,
      phase_results: [],
    } as unknown as RunResponse

    const wrapper = mount(DataMetricsCard)

    // 饱和度统一以小数呈现，不再使用百分比
    expect(wrapper.text()).toContain('0.88')
    expect(wrapper.text()).not.toContain('88.0%')
  })

  it('renders summary mode without per-approach detail rows', () => {
    const s = usePresentationStore()
    s.applySnapshot(
      snap({
        ...baseMetrics(),
        los: 'F',
        by_approach: [{ approach: '东进口', saturation: 3.49, delay_index: 1.8, los: 'F' }],
        by_movement: [{ movement: '东左转', saturation: 1.77, green_utilization: 1.77, level: '过饱和' }],
        imbalance_index: 0.46,
        approach_count: 4,
        lane_count: 26,
      }),
    )
    const wrapper = mount(DataMetricsCard, { props: { variant: 'summary' } })
    const text = wrapper.text()
    expect(text).toContain('运行数据摘要')
    expect(text).toContain('详细逐进口/逐转向数据见左下')
    expect(wrapper.find('[data-testid="metrics-detail"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="metrics-summary"]').exists()).toBe(true)
    expect(text).not.toContain('东左转')
  })
})
