import { describe, it, expect } from 'vitest'
import { buildActs } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import fixture from '@/mock/run_1_fixture.json'

describe('buildActs', () => {
  it('produces nine acts from the real fixture', () => {
    const acts = buildActs(fixture as unknown as RunResponse)
    expect(acts).toHaveLength(9)
    expect(acts[0].reveal).toBe('ticket')
    expect(acts[7].reveal).toBe('plan')
    expect(acts[8].id).toBe('act9_feedback')
    // 每幕都有可展示旁白（真实字段），不为空
    for (const a of acts) expect(a.narration.length).toBeGreaterThan(0)
  })

  it('degrades gracefully on empty response (no throw, still 9 acts)', () => {
    const empty = {
      trace_id: null,
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: {},
      plan: null,
      phase_results: [],
    } as RunResponse
    const acts = buildActs(empty)
    expect(acts).toHaveLength(9)
    expect(acts[0].scene.kind).toBe('city')
  })
})
