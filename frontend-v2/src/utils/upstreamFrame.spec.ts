import { describe, expect, it } from 'vitest'
import { isEdgeId, visibleAtFrame } from './upstreamFrame'

const SB = {
  trees: [], frames: [
    { idx: 0, tree: 'N', focus: 'T', center: [0, 0], zoom: 16, fit: false, reveal: ['T'] },
    { idx: 1, tree: 'N', focus: 'up1', center: [1, 1], zoom: 15, fit: false, reveal: ['up1', 'edge:N:T-up1'] },
    { idx: 2, tree: 'N', focus: ['up1'], center: null, zoom: null, fit: true, reveal: ['up1', 'edge:N:T-up1'] },
    { idx: 3, tree: 'E', focus: 'T', center: [0, 0], zoom: 16, fit: false, reveal: ['T'] },
    { idx: 4, tree: 'E', focus: 'up2', center: [2, 2], zoom: 15, fit: false, reveal: ['up2', 'edge:E:T-up2'] },
  ],
} as any

describe('visibleAtFrame', () => {
  it('accumulates reveal ids up to n', () => {
    const v = visibleAtFrame(SB, 1)
    expect([...v.overlayIds].sort()).toEqual(['T', 'edge:N:T-up1', 'up1'])
    expect(v.activeTree).toBe('N')
  })
  it('exposes camera center/zoom/fit for auto cinematics', () => {
    const v = visibleAtFrame(SB, 1)
    expect(v.center).toEqual([1, 1])
    expect(v.zoom).toBe(15)
    expect(v.fit).toBe(false)
    expect(visibleAtFrame(SB, 2).fit).toBe(true)
  })
  it('rewinding drops later overlays (frame reconstruction)', () => {
    expect([...visibleAtFrame(SB, 0).overlayIds]).toEqual(['T'])
  })
  it('switches active tree at handoff', () => {
    expect(visibleAtFrame(SB, 4).activeTree).toBe('E')
  })
})

describe('isEdgeId', () => {
  it('distinguishes edges from node ids', () => {
    expect(isEdgeId('edge:N:T-up1')).toBe(true)
    expect(isEdgeId('up1')).toBe(false)
  })
})
