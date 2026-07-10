import { describe, it, expect } from 'vitest'
import { hasCoord, validPath, nonEmpty } from '@/utils/guards'
import { deriveVC, vcColor } from '@/utils/vc'

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
