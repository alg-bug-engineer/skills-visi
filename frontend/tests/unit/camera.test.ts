import { describe, it, expect } from 'vitest'
import { clampZoomUp, drillSteps } from '@/map/amapUtils'
import { lerpPath } from '@/map/MapController'

describe('drillSteps (coherent monotonic drill, no flicker)', () => {
  it('city → intersection: 11 → 16 ascends through anchors', () => {
    const steps = drillSteps(11, 16)
    expect(steps).toEqual([14, 16])
  })

  it('intersection → lane: 16 → 18 never zooms out (no step below current)', () => {
    const steps = drillSteps(16, 18)
    for (const z of steps) expect(z).toBeGreaterThan(16)
    // strictly ascending
    for (let i = 1; i < steps.length; i++) expect(steps[i]).toBeGreaterThan(steps[i - 1])
    expect(steps[steps.length - 1]).toBe(18)
  })

  it('already-zoomed 16 → 17 does not fly back to anchor 14', () => {
    const steps = drillSteps(16, 17)
    expect(steps.some((z) => z < 16)).toBe(false)
    expect(steps).toEqual([16.2, 17])
  })

  it('target not above current returns just the target (pullback handled elsewhere)', () => {
    expect(drillSteps(18, 17)).toEqual([17])
    expect(drillSteps(17, 17)).toEqual([17])
  })

  it('every step is strictly ascending and ends at target for a deep drill', () => {
    const steps = drillSteps(11, 18)
    expect(steps).toEqual([14, 16.2, 17.5, 18])
  })
})

describe('clampZoomUp', () => {
  it('never returns below current', () => {
    expect(clampZoomUp(16, 15)).toBe(16)
    expect(clampZoomUp(11, 16)).toBe(16)
  })
})

describe('lerpPath (retained for regression)', () => {
  it('clamps and interpolates', () => {
    expect(lerpPath([[0, 0], [10, 0]], 0.5)).toEqual([5, 0])
    expect(lerpPath([[0, 0], [10, 0]], 2)).toEqual([10, 0])
    expect(lerpPath([], 0.5)).toEqual([0, 0])
  })
})
