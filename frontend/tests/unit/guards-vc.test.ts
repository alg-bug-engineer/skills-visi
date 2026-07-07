import { describe, it, expect } from 'vitest'
import { hasCoord, validPath, nonEmpty } from '@/utils/guards'
import { deriveVC, vcColor } from '@/utils/vc'
import { lerpPath } from '@/map/MapController'

describe('guards', () => {
  it('hasCoord rejects null/NaN', () => {
    expect(hasCoord(117.1, 36.6)).toBe(true)
    expect(hasCoord(null, 36.6)).toBe(false)
    expect(hasCoord(117.1, NaN)).toBe(false)
  })
  it('validPath filters invalid points', () => {
    expect(validPath([[1, 2], [null, 3], [4, 5]] as unknown)).toEqual([
      [1, 2],
      [4, 5],
    ])
    expect(validPath(null)).toEqual([])
  })
  it('nonEmpty', () => {
    expect(nonEmpty([1])).toBe(true)
    expect(nonEmpty([])).toBe(false)
    expect(nonEmpty(null)).toBe(false)
  })
})

describe('vc (no fabrication)', () => {
  it('returns null when inputs missing', () => {
    expect(deriveVC(undefined, 10)).toBeNull()
    expect(deriveVC(10, 0)).toBeNull()
    expect(deriveVC(10, null)).toBeNull()
  })
  it('computes ratio when valid', () => {
    expect(deriveVC(8, 10)).toBeCloseTo(0.8)
  })
  it('vcColor null passthrough', () => {
    expect(vcColor(null)).toBeNull()
    expect(vcColor(1.2)).toContain('hsl')
  })
})

describe('lerpPath', () => {
  it('interpolates midpoint', () => {
    expect(lerpPath([[0, 0], [10, 20]], 0.5)).toEqual([5, 10])
  })
  it('clamps and handles degenerate', () => {
    expect(lerpPath([[3, 4]], 0.9)).toEqual([3, 4])
    expect(lerpPath([], 0.5)).toEqual([0, 0])
    expect(lerpPath([[0, 0], [10, 0]], 2)).toEqual([10, 0])
  })
})
