import { describe, it, expect } from 'vitest'
import { ACT_DEFS, narrationFor, phaseReady } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import fixture from '@/mock/run_1_fixture.json'

const fx = fixture as unknown as RunResponse

describe('ACT_DEFS', () => {
  it('defines nine acts with phase mapping', () => {
    expect(ACT_DEFS).toHaveLength(9)
    expect(ACT_DEFS[0].reveal).toBe('ticket')
    expect(ACT_DEFS[0].phase).toBe('intent')
    expect(ACT_DEFS[7].reveal).toBe('plan')
    expect(ACT_DEFS[7].phase).toBe('plan')
    expect(ACT_DEFS[8].id).toBe('act9_feedback')
  })
})

describe('narrationFor', () => {
  it('produces non-empty narration for every act from the real fixture', () => {
    for (const act of ACT_DEFS) {
      expect(narrationFor(act, fx).length).toBeGreaterThan(0)
    }
  })

  it('degrades gracefully with null response (no throw)', () => {
    for (const act of ACT_DEFS) {
      expect(() => narrationFor(act, null)).not.toThrow()
    }
  })
})

describe('phaseReady (streaming gate)', () => {
  it('is false on empty response', () => {
    const empty = { phases: {}, plan: null } as unknown as RunResponse
    expect(phaseReady(empty, 'intent')).toBe(false)
    expect(phaseReady(null, 'diagnosis')).toBe(false)
  })

  it('detects phase presence incrementally', () => {
    const snap = { phases: { intent: {}, diagnosis: {} }, plan: null } as unknown as RunResponse
    expect(phaseReady(snap, 'intent')).toBe(true)
    expect(phaseReady(snap, 'diagnosis')).toBe(true)
    expect(phaseReady(snap, 'cause')).toBe(false)
    expect(phaseReady(snap, 'plan')).toBe(false)
  })

  it('plan gate checks the plan block', () => {
    const snap = { phases: {}, plan: { candidates: [] } } as unknown as RunResponse
    expect(phaseReady(snap, 'plan')).toBe(true)
  })
})
