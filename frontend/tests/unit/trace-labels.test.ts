import { describe, it, expect } from 'vitest'
import {
  buildUpstreamLabelHtml,
  coverageNodeStyle,
  formatFeedDirection,
  turnLabelFromMovement,
  upstreamEdgeStrokeWeight,
} from '@/map/traceLabels'

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

describe('buildUpstreamLabelHtml (no fabrication)', () => {
  it('shows real coverage', () => {
    const html = buildUpstreamLabelHtml({ name: '奥体西路与经十路路口', coverage: 71.63 })
    expect(html).toContain('奥体西路与经十路')
    expect(html).toContain('71.6%')
  })

  it('falls back to 拓扑 when coverage missing (no invented %)', () => {
    const html = buildUpstreamLabelHtml({ name: '转山西路', coverage: null })
    expect(html).toContain('拓扑')
    expect(html).not.toContain('%')
  })
})
