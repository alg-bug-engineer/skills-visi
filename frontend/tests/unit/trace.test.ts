import { describe, it, expect } from 'vitest'
import {
  approxPathLength,
  interpolatePath,
  orientPathFromOrigin,
  particleDurationFor,
  pathPrefix,
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
import { propagationColor, roadColorForFunctionalClass } from '@/map/mapPalette'
import { TraceLayer } from '@/map/traceLayer'

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

  it('uses geographic distance instead of vertex count', () => {
    expect(interpolatePath([[0, 0], [9, 0], [10, 0]], 0.5)).toEqual([5, 0])
  })

  it('returns null for empty path and self for single point', () => {
    expect(interpolatePath([], 0.5)).toBeNull()
    expect(interpolatePath([[3, 4]], 0.9)).toEqual([3, 4])
  })
})

describe('upstream spread geometry', () => {
  it('orients a supplied real path from target toward upstream without offset geometry', () => {
    const path: LngLat[] = [[10, 0], [5, 0], [0, 0]]
    expect(orientPathFromOrigin(path, [0, 0])).toEqual([[0, 0], [5, 0], [10, 0]])
  })

  it('builds a progressive prefix that stays exactly on the source polyline', () => {
    expect(pathPrefix([[0, 0], [9, 0], [10, 0]], 0.5)).toEqual([[0, 0], [5, 0]])
    expect(pathPrefix([[0, 0], [9, 0], [10, 0]], 1)).toEqual([[0, 0], [9, 0], [10, 0]])
  })
})

describe('flow trace visualization isolation', () => {
  it('uses one trace color and does not create particle markers as fake flow points', () => {
    const markers: Array<{ options: Record<string, unknown> }> = []
    const polylines: Array<{ options: Record<string, unknown> }> = []
    class FakeOverlay {
      options: Record<string, unknown>
      constructor(options: Record<string, unknown>) { this.options = options }
      setMap() {}
      setPath(path: unknown) { this.options.path = path }
      on() {}
      setOptions() {}
    }
    class FakeMarker extends FakeOverlay {
      constructor(options: Record<string, unknown>) {
        super(options)
        markers.push(this)
      }
    }
    class FakePolyline extends FakeOverlay {
      constructor(options: Record<string, unknown>) {
        super(options)
        polylines.push(this)
      }
    }
    const layer = new TraceLayer(
      {
        Marker: FakeMarker,
        Polyline: FakePolyline,
        CircleMarker: FakeOverlay,
        Pixel: class { constructor(public x: number, public y: number) {} },
      },
      {},
    )

    layer.renderSegmentCoverage({
      available: true,
      trace_direction: 'upstream',
      target: { id: 'T', name: '目标', lng: 117.1, lat: 36.6, target_flow: 10 },
      links: [{ id: 'L', name: '真实路段', ratio: 0.5, coords: [[117.1, 36.6], [117.09, 36.61]] }],
      intersections: [],
      visualization: { particle_color: '#39dfff' },
    })

    expect(markers.some((marker) => String(marker.options.content).includes('map-flow-particle'))).toBe(false)
    expect(new Set(polylines.map((line) => line.options.strokeColor))).toEqual(new Set(['#39dfff']))
    layer.reset()
  })
})

describe('3D source traffic palette', () => {
  it('maps target-to-source spread to severe, high, medium and low source colors', () => {
    expect(propagationColor(0, 10)).toBe('#ff3c1f')
    expect(propagationColor(3, 10)).toBe('#ff8d1f')
    expect(propagationColor(6, 10)).toBe('#ffd247')
    expect(propagationColor(9, 10)).toBe('#39dfff')
  })

  it('maps PostgreSQL fc to the same road hierarchy as the 3D source', () => {
    expect(roadColorForFunctionalClass(2)).toBe('#ffc640')
    expect(roadColorForFunctionalClass(3)).toBe('#5ccfff')
    expect(roadColorForFunctionalClass(4)).toBe('#2189ff')
    expect(roadColorForFunctionalClass(5)).toBe('#1f4d7c')
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
