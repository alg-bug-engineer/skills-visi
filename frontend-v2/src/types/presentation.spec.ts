import { describe, expect, it } from 'vitest'
import {
  createInitialPresentation,
  isPresentationDimActive,
  shouldShowTimingRingMini,
} from './presentation'

function withRing() {
  const state = createInitialPresentation()
  state.evidence = {
    timing_profile: { ring_diagram: { available: true } },
  } as unknown as typeof state.evidence
  return state
}

describe('isPresentationDimActive', () => {
  it('is permissive when activeDimensions unknown/empty', () => {
    expect(isPresentationDimActive([], 'ring')).toBe(true)
    expect(isPresentationDimActive(undefined, 'ring')).toBe(true)
  })

  it('gates by membership when dimensions known', () => {
    expect(isPresentationDimActive(['flow', 'queue'], 'ring')).toBe(false)
    expect(isPresentationDimActive(['flow', 'ring'], 'ring')).toBe(true)
  })
})

describe('shouldShowTimingRingMini · 配时环图按需出现', () => {
  it('hides ring for 拥堵 (ring dimension not active)', () => {
    const state = withRing()
    state.activeDimensions = ['flow', 'channelization', 'saturation', 'queue', 'delay']
    expect(shouldShowTimingRingMini('timing', state)).toBe(false)
  })

  it('shows ring for 空放 at evidence phase', () => {
    const state = withRing()
    state.activeDimensions = ['green_util', 'timing_plan', 'ring', 'cycle']
    expect(shouldShowTimingRingMini('evidence', state)).toBe(true)
    expect(shouldShowTimingRingMini('rule', state)).toBe(true)
  })

  it('stays permissive when activeDimensions empty (unknown)', () => {
    const state = withRing()
    expect(shouldShowTimingRingMini('timing', state)).toBe(true)
  })
})
