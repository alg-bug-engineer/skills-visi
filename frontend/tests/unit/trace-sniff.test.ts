import { describe, expect, it } from 'vitest'
import { buildLegacySniffScene, summarizeSniffScene, type TraceSniffScene } from '@/map/traceSniff'

const scene: TraceSniffScene = {
  available: true,
  trace_direction: 'upstream',
  intersections: [
    {
      inter_id: 'T',
      name: '目标',
      center: [117.1, 36.6],
      role: 'target',
      in_main_corridor: false,
      links: [{ link_id: 'L0', link_role: 'entrance', path: [[117.09, 36.6], [117.1, 36.6]] }],
    },
    {
      inter_id: 'M',
      name: '主链',
      center: [117.09, 36.6],
      role: 'upstream',
      path_coverage: 72,
      in_main_corridor: true,
      links: [{ link_id: 'L1', link_role: 'exit', path: [[117.09, 36.6], [117.1, 36.6]] }],
    },
    {
      inter_id: 'O',
      name: '其他来向',
      center: [117.08, 36.61],
      role: 'upstream',
      path_coverage: 18,
      in_main_corridor: false,
      links: [{ link_id: 'L2', link_role: 'exit', path: [[117.08, 36.61], [117.1, 36.6]] }],
    },
  ],
}

describe('summarizeSniffScene', () => {
  it('separates target, main corridor and other real links', () => {
    expect(summarizeSniffScene(scene)).toEqual({
      targetLinks: 1,
      mainLinks: 1,
      otherLinks: 1,
      visibleNodes: 3,
    })
  })
})

describe('buildLegacySniffScene', () => {
  it('reuses existing real paths as sniff target/main links without fabricating geometry', () => {
    const legacy = buildLegacySniffScene({
      target: { inter_id: 'T', inter_name: '目标', lng: 117.1, lat: 36.6 },
      channelizationMap: {
        links: [{ link_id: 'L0', link_role: 'entrance', path: [[117.09, 36.6], [117.1, 36.6]] }],
      },
      upstreamTraces: [
        {
          upstream_inter_id: 'U',
          upstream_inter_name: '上游',
          upstream_lng: 117.09,
          upstream_lat: 36.6,
          path: [[117.09, 36.6], [117.1, 36.6]],
          dominant_movement: { share_pct: 73 },
        },
      ],
    })

    expect(legacy.available).toBe(true)
    expect(legacy.trace_direction).toBe('upstream')
    expect(legacy.intersections).toHaveLength(2)
    expect(legacy.intersections?.[0].links?.[0].link_id).toBe('L0')
    expect(legacy.intersections?.[1].in_main_corridor).toBe(true)
    expect(legacy.intersections?.[1].path_coverage).toBe(73)
  })
})
