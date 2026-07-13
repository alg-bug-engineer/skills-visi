import { describe, it, expect } from 'vitest'
import {
  approxPathLength,
  interpolatePath,
  particleDurationFor,
  sampleAlongPath,
  type LngLat,
} from '@/map/traceParticles'
import {
  buildUpstreamLabelHtml,
  coverageNodeStyle,
  formatFeedDirection,
  turnLabelFromMovement,
  upstreamEdgeStrokeWeight,
} from '@/map/traceLabels'
import { buildLegacySniffScene, summarizeSniffScene, type TraceSniffScene } from '@/map/traceSniff'

const PATH: LngLat[] = [
  [0, 0],
  [10, 0],
  [10, 10],
]

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

describe('interpolatePath', () => {
  it('clamps endpoints', () => {
    expect(interpolatePath(PATH, 0)).toEqual([0, 0])
    expect(interpolatePath(PATH, 1)).toEqual([10, 10])
    expect(interpolatePath(PATH, -5)).toEqual([0, 0])
    expect(interpolatePath(PATH, 5)).toEqual([10, 10])
  })

  it('interpolates linearly within a segment', () => {
    expect(interpolatePath(PATH, 0.25)).toEqual([5, 0])
  })

  it('returns null for empty path and self for single point', () => {
    expect(interpolatePath([], 0.5)).toBeNull()
    expect(interpolatePath([[3, 4]], 0.9)).toEqual([3, 4])
  })
})

describe('sampleAlongPath', () => {
  it('returns count points including both endpoints', () => {
    const pts = sampleAlongPath(PATH, 3)
    expect(pts).toHaveLength(3)
    expect(pts[0]).toEqual([0, 0])
    expect(pts[2]).toEqual([10, 10])
  })

  it('handles degenerate inputs', () => {
    expect(sampleAlongPath([], 5)).toEqual([])
    expect(sampleAlongPath(PATH, 0)).toEqual([])
    expect(sampleAlongPath(PATH, 1)).toEqual([[0, 0]])
  })
})

describe('approxPathLength', () => {
  it('sums segment lengths', () => {
    expect(approxPathLength(PATH)).toBeCloseTo(20, 6)
    expect(approxPathLength([])).toBe(0)
  })
})

describe('particleDurationFor', () => {
  it('is clamped to [1200, 2800] and longer paths are slower', () => {
    const short = particleDurationFor([[0, 0], [0.0001, 0]])
    const long = particleDurationFor([[0, 0], [0.02, 0]])
    expect(short).toBeGreaterThanOrEqual(1200)
    expect(long).toBeLessThanOrEqual(2800)
    expect(long).toBeGreaterThanOrEqual(short)
  })
})

describe('coverageNodeStyle', () => {
  it('grows monotonically with coverage', () => {
    const low = coverageNodeStyle(0)
    const mid = coverageNodeStyle(50)
    const high = coverageNodeStyle(100)
    expect(low.size).toBeLessThan(mid.size)
    expect(mid.size).toBeLessThan(high.size)
    expect(high.opacity).toBeCloseTo(1, 5)
  })
})

describe('upstreamEdgeStrokeWeight', () => {
  it('is bounded and increases with flow', () => {
    expect(upstreamEdgeStrokeWeight(0)).toBeCloseTo(2.8, 5)
    expect(upstreamEdgeStrokeWeight(100)).toBeGreaterThan(upstreamEdgeStrokeWeight(20))
    expect(upstreamEdgeStrokeWeight(null)).toBeCloseTo(2.8, 5)
  })
})

describe('formatFeedDirection', () => {
  it('maps dir8 + turn to chinese', () => {
    expect(formatFeedDirection(2, 2)).toBe('东直行')
    expect(formatFeedDirection(6, 1)).toBe('西左转')
  })
})

describe('turnLabelFromMovement', () => {
  it('normalizes english movement to chinese turn', () => {
    expect(turnLabelFromMovement('through')).toBe('直行')
    expect(turnLabelFromMovement('left')).toBe('左转')
    expect(turnLabelFromMovement('right')).toBe('右转')
  })
})

describe('buildUpstreamLabelHtml', () => {
  it('shows real coverage as target-flow share', () => {
    const html = buildUpstreamLabelHtml({ name: '奥体西路与经十路路口', coverage: 71.63 })
    expect(html).toContain('奥体西路与经十路')
    expect(html).toContain('占目标流量 71.6%')
    expect(html).not.toContain('途经')
  })

  it('falls back to topology label when coverage missing', () => {
    const html = buildUpstreamLabelHtml({ name: '转山西路', coverage: null })
    expect(html).toContain('拓扑关联')
    expect(html).not.toContain('%')
  })
})

describe('summarizeSniffScene', () => {
  it('separates target, main corridor and other real links', () => {
    expect(summarizeSniffScene(scene)).toEqual({
      targetLinks: 1,
      mainLinks: 1,
      otherLinks: 1,
      visibleNodes: 3,
    })
  })

  it('hides finite flow coverage below 10 percent', () => {
    const low: TraceSniffScene = {
      available: true,
      trace_direction: 'upstream',
      intersections: [
        scene.intersections![0],
        {
          inter_id: 'LOW',
          name: '低占比',
          center: [117.07, 36.6],
          role: 'upstream',
          path_coverage: 9.9,
          in_main_corridor: true,
          links: [{ link_id: 'L-low', path: [[117.07, 36.6], [117.1, 36.6]] }],
        },
      ],
    }

    expect(summarizeSniffScene(low)).toEqual({
      targetLinks: 1,
      mainLinks: 0,
      otherLinks: 0,
      visibleNodes: 1,
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
