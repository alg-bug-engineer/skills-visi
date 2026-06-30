import { describe, expect, it } from 'vitest'
import { visibleAtFrame } from './upstreamFrame'

const SB = {
  trees: [], frames: [
    { idx: 0, tree: 'N', kind: 'thesis', focus: 'target', reveal: [] },
    { idx: 1, tree: 'N', kind: 'hop1', focus: 'up1', reveal: ['edge:N-up1'] },
    { idx: 2, tree: 'N', kind: 'inspect', focus: 'up1', reveal: ['ring:up1'] },
    { idx: 3, tree: 'E', kind: 'thesis', focus: 'target', reveal: [] },
    { idx: 4, tree: 'E', kind: 'hop1', focus: 'up1', reveal: ['edge:E-up1'] },
  ],
} as any

describe('visibleAtFrame', () => {
  it('accumulates reveal ids up to n', () => {
    const v = visibleAtFrame(SB, 2)
    expect([...v.overlayIds].sort()).toEqual(['edge:N-up1', 'ring:up1'])
    expect(v.activeTree).toBe('N')
  })
  it('rewinding drops later overlays (frame reconstruction)', () => {
    expect([...visibleAtFrame(SB, 1).overlayIds]).toEqual(['edge:N-up1'])
    expect([...visibleAtFrame(SB, 0).overlayIds]).toEqual([])
  })
  it('switches active tree at handoff', () => {
    expect(visibleAtFrame(SB, 4).activeTree).toBe('E')
  })
})
