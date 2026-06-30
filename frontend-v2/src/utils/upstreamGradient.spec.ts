import { describe, expect, it } from 'vitest'
import { colorAtGradientProgress, segmentPathWithGradient } from './upstreamGradient'

describe('upstreamGradient', () => {
  it('interpolates from white toward green', () => {
    expect(colorAtGradientProgress(0)).toBe('#ffffff')
    expect(colorAtGradientProgress(1)).toBe('#00e676')
    const mid = colorAtGradientProgress(0.5)
    expect(mid).not.toBe('#ffffff')
    expect(mid).not.toBe('#00e676')
  })

  it('splits a straight path into gradient segments', () => {
    const segs = segmentPathWithGradient(
      [
        [0, 0],
        [1, 0],
      ],
      4,
    )
    expect(segs).toHaveLength(4)
    expect(segs[0].progress).toBeLessThan(segs[3].progress)
    expect(segs[0].path[0][0]).toBeCloseTo(0, 5)
    expect(segs[3].path[1][0]).toBeCloseTo(1, 5)
  })
})
