/**
 * 需求 33：路段覆盖场景消费契约（前端只呈现后端真实字段）。
 */
import { describe, expect, it } from 'vitest'

type CoverageScene = {
  available?: boolean
  links?: Array<{ coords?: number[][]; ratio?: number }>
  intersections?: Array<{ lng?: number; lat?: number; ratio?: number }>
}

function coverageBounds(scene: CoverageScene, target: [number, number]): [number, number][] {
  const pts: [number, number][] = [target]
  if (!scene.available) return pts
  for (const link of scene.links ?? []) {
    for (const c of link.coords ?? []) {
      if (Array.isArray(c) && c.length >= 2) pts.push([c[0], c[1]])
    }
  }
  for (const inter of scene.intersections ?? []) {
    if (inter.lng != null && inter.lat != null) pts.push([inter.lng, inter.lat])
  }
  return pts
}

function strokeWeight(ratio: number): number {
  return Math.max(4, Math.min(14, 3 + ratio * 38))
}

describe('segment coverage contract', () => {
  it('collects bounds from real link coords only', () => {
    const pts = coverageBounds(
      {
        available: true,
        links: [{ coords: [[117.0, 36.6], [117.01, 36.61]], ratio: 0.2 }],
        intersections: [{ lng: 117.02, lat: 36.62, ratio: 0.15 }],
      },
      [117.0, 36.6],
    )
    expect(pts.length).toBe(4)
  })

  it('skips unavailable scene geometry', () => {
    const pts = coverageBounds({ available: false, links: [{ coords: [[1, 2], [3, 4]] }] }, [117, 36])
    expect(pts).toEqual([[117, 36]])
  })

  it('maps ratio to stroke weight like reference drawResult', () => {
    expect(strokeWeight(0)).toBe(4)
    expect(strokeWeight(0.2)).toBe(Math.max(4, Math.min(14, 3 + 0.2 * 38)))
    expect(strokeWeight(1)).toBe(14)
  })
})
