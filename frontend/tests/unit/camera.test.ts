import { describe, it, expect } from 'vitest'
import {
  boundsFromPoints,
  bearingFromDirectionLabel,
  clampZoomUp,
  drillSteps,
  offsetLngLatByMeters,
  samplePathForBounds,
} from '@/map/amapUtils'
import { lerpPath } from '@/map/MapController'
import { findArmForDirection } from '@/map/channelizationGeometry'

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

describe('boundsFromPoints', () => {
  it('computes sw/ne envelope', () => {
    const b = boundsFromPoints([[117, 36], [117.01, 36.01], [117.005, 35.995]])
    expect(b?.sw).toEqual([117, 35.995])
    expect(b?.ne).toEqual([117.01, 36.01])
  })

  it('returns null for empty', () => {
    expect(boundsFromPoints([])).toBeNull()
  })
})

describe('bearingFromDirectionLabel', () => {
  it('maps cardinal directions', () => {
    expect(bearingFromDirectionLabel('东')).toBe(90)
    expect(bearingFromDirectionLabel('西')).toBe(270)
    expect(bearingFromDirectionLabel('西向东')).toBe(90)
  })
})

describe('offsetLngLatByMeters', () => {
  it('offsets northward', () => {
    const [lng, lat] = offsetLngLatByMeters([117, 36], 0, 1000)
    expect(lat).toBeGreaterThan(36)
    expect(lng).toBeCloseTo(117, 3)
  })
})

describe('samplePathForBounds', () => {
  it('samples long paths for corridor fitBounds', () => {
    const path: [number, number][] = Array.from({ length: 20 }, (_, i) => [117 + i * 0.001, 36.65])
    const sampled = samplePathForBounds(path, 5)
    expect(sampled).toHaveLength(5)
    expect(sampled[0]).toEqual(path[0])
    expect(sampled[4]).toEqual(path[19])
  })
})

describe('findArmForDirection', () => {
  it('matches dir8_label on inLink', () => {
    const arm = findArmForDirection(
      [{ angle: 90, inLink: { dir8_label: '东', link_role: 'entrance' }, outLink: null }],
      '东',
    )
    expect(arm?.inLink?.dir8_label).toBe('东')
  })
})
