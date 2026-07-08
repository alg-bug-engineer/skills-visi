import { describe, expect, it } from 'vitest'
import type { RunResponse } from '@/api/types'
import { buildHudMetrics, buildMetricMarkers } from '@/map/mapMarkers'

const response = {
  diagnosis_ticket: {
    direction: '东向西',
  },
  phases: {
    diagnosis: {
      metrics: {
        queue_ratio: 0.2,
        saturation_rate: 0.88,
        green_utilization: 0.57,
      },
    },
  },
} as unknown as RunResponse

describe('map markers', () => {
  it('uses saturation_rate when saturation alias is absent', () => {
    expect(buildHudMetrics(response)).toContainEqual({
      label: '饱和度',
      value: '88.0%',
      severity: 'high',
    })

    const markers = buildMetricMarkers(response, [117, 36.6])
    expect(markers.some((marker) => marker.title === '东向西向饱和' && marker.value === '88.0%')).toBe(true)
  })
})
