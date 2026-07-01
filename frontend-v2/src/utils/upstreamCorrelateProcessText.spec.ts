import { describe, expect, it } from 'vitest'
import { buildCorrelateProcessText, upstreamCorrelateDurationMs } from './upstreamCorrelateProcessText'
import type { UpstreamCorrelateMap } from '../types/map'

const sampleMap: UpstreamCorrelateMap = {
  approach: '西进口',
  dir8_code: 6,
  turn_dir_no: 2,
  stats: { distinct_upstream: 37, main_corridor_count: 18 },
  main_corridor_chain: [
    { hop: 1, inter_id: 'u1', name: '经十路与转山西路路口', path_coverage: 90.1 },
    { hop: 2, inter_id: 'u2', name: '经十路辅路与洪山路路口', path_coverage: 76.5 },
  ],
  intersections: [
    { inter_id: 't', name: '目标', center: [0, 0], role: 'target', links: [] },
    { inter_id: 'u1', name: '上游1', center: [1, 1], role: 'upstream', path_coverage: 90, links: [] },
  ],
}

describe('upstreamCorrelateProcessText', () => {
  it('summarizes distinct upstream and main corridor chain', () => {
    const text = buildCorrelateProcessText(sampleMap, '西直行')
    expect(text).toContain('37 个')
    expect(text).toContain('主走廊')
    expect(text).toContain('经十路与转山西路路口')
  })

  it('duration scales with intersection count', () => {
    expect(upstreamCorrelateDurationMs(sampleMap)).toBeGreaterThan(3000)
    expect(upstreamCorrelateDurationMs(null)).toBeGreaterThan(0)
  })
})
