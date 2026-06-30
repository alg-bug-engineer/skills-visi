import { describe, expect, it } from 'vitest'
import {
  approxPathLength,
  interpolatePath,
  particleDurationFor,
  sampleAlongPath,
  type LngLat,
} from './traceParticles'

const PATH: LngLat[] = [
  [0, 0],
  [2, 0],
  [2, 2],
]

describe('interpolatePath', () => {
  it('returns endpoints at t=0 and t=1', () => {
    expect(interpolatePath(PATH, 0)).toEqual([0, 0])
    expect(interpolatePath(PATH, 1)).toEqual([2, 2])
  })

  it('interpolates the midpoint along the polyline', () => {
    // 两段等长，t=0.5 落在第一段末端 [2,0]
    expect(interpolatePath(PATH, 0.5)).toEqual([2, 0])
  })

  it('clamps out-of-range t', () => {
    expect(interpolatePath(PATH, -1)).toEqual([0, 0])
    expect(interpolatePath(PATH, 5)).toEqual([2, 2])
  })

  it('returns null for empty path', () => {
    expect(interpolatePath([], 0.5)).toBeNull()
  })
})

describe('sampleAlongPath', () => {
  it('samples the requested count including endpoints', () => {
    const pts = sampleAlongPath(PATH, 3)
    expect(pts).toHaveLength(3)
    expect(pts[0]).toEqual([0, 0])
    expect(pts[2]).toEqual([2, 2])
  })

  it('returns empty for zero count or empty path', () => {
    expect(sampleAlongPath(PATH, 0)).toEqual([])
    expect(sampleAlongPath([], 5)).toEqual([])
  })
})

describe('particleDurationFor', () => {
  it('clamps within 1200~2800ms', () => {
    expect(particleDurationFor([[0, 0]])).toBe(1200)
    const long = particleDurationFor([
      [0, 0],
      [1, 1],
    ])
    expect(long).toBeGreaterThanOrEqual(1200)
    expect(long).toBeLessThanOrEqual(2800)
  })

  it('grows with path length', () => {
    const short = particleDurationFor([
      [0, 0],
      [0.001, 0],
    ])
    const longer = particleDurationFor([
      [0, 0],
      [0.01, 0],
    ])
    expect(longer).toBeGreaterThan(short)
  })
})

describe('approxPathLength', () => {
  it('sums segment lengths', () => {
    expect(approxPathLength(PATH)).toBeCloseTo(4, 6)
  })
})
