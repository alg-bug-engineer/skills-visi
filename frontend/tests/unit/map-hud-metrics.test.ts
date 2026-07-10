import { describe, expect, it } from 'vitest'
import { buildHudMetrics, buildMetricMarkers } from '@/map/mapMarkers'
import type { RunResponse } from '@/api/types'

function snap(metrics: Record<string, unknown>): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: { diagnosis: { metrics, data_source: 'pg' } },
    plan: null,
    phase_results: [],
  } as unknown as RunResponse
}

describe('buildHudMetrics (左上角运行数据 HUD)', () => {
  it('renders saturation / green utilization as decimals, not percentages', () => {
    const items = buildHudMetrics(
      snap({ queue_ratio: 0.18, saturation: 0.87, green_utilization: 0.5741, storage_length_m: 884 }),
    )
    const sat = items.find((m) => m.label === '饱和度')
    const gu = items.find((m) => m.label === '绿灯利用率')
    expect(sat?.value).toBe('0.87')
    expect(gu?.value).toBe('0.57')
    expect(items.some((m) => m.value.includes('%'))).toBe(false)
  })

  it('includes 方向失衡 and 进口道长度 (queue-ratio denominator)', () => {
    const items = buildHudMetrics(
      snap({
        queue_ratio: 0.18,
        queue_length_m: 158,
        storage_length_m: 883.94,
        saturation: 0.87,
        green_utilization: 0.57,
        imbalance_index: 0.46,
      }),
    )
    const imb = items.find((m) => m.label === '方向失衡')
    const approach = items.find((m) => m.label === '进口道长度')
    expect(imb?.value).toBe('0.46')
    expect(approach?.value).toBe('884m')
  })

  it('omits optional cells when fields are absent (no fabrication)', () => {
    const items = buildHudMetrics(snap({ queue_ratio: 0.18 }))
    expect(items.some((m) => m.label === '方向失衡')).toBe(false)
    expect(items.some((m) => m.label === '进口道长度')).toBe(false)
  })
})

describe('buildMetricMarkers (地图方向气泡)', () => {
  it('renders direction saturation as decimal, consistent with HUD', () => {
    const resp = snap({ saturation: 0.87, queue_ratio: 0.18 }) as RunResponse
    resp.diagnosis_ticket = { ...(resp.diagnosis_ticket ?? {}), direction: '东' } as RunResponse['diagnosis_ticket']
    const markers = buildMetricMarkers(resp, [117.0, 36.65])
    const sat = markers.find((m) => m.title.includes('饱和'))
    expect(sat?.value).toBe('0.87')
    expect(sat?.value.includes('%')).toBe(false)
  })
})
