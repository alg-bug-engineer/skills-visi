import { describe, it, expect } from 'vitest'
import {
  approxPathLength,
  interpolatePath,
  particleDurationFor,
  sampleAlongPath,
  type LngLat,
} from '@/map/traceParticles'

const PATH: LngLat[] = [
  [0, 0],
  [10, 0],
  [10, 10],
]

describe('interpolatePath', () => {
  it('clamps endpoints', () => {
    expect(interpolatePath(PATH, 0)).toEqual([0, 0])
    expect(interpolatePath(PATH, 1)).toEqual([10, 10])
    expect(interpolatePath(PATH, -5)).toEqual([0, 0])
    expect(interpolatePath(PATH, 5)).toEqual([10, 10])
  })

  it('interpolates linearly within a segment (t=0.25 → mid of first segment)', () => {
    // total 2 segments; t=0.25 → half of first segment → [5,0]
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
