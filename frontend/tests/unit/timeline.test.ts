import { describe, it, expect } from 'vitest'
import { ACT_DEFS, narrationFor, phaseReady, summaryFor } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import fixture from '@/mock/run_1_fixture.json'

const fx = fixture as unknown as RunResponse

describe('ACT_DEFS', () => {
  it('defines nine acts with evidence → attribution → cases → plan order', () => {
    expect(ACT_DEFS).toHaveLength(9)
    expect(ACT_DEFS[0].reveal).toBe('ticket')
    expect(ACT_DEFS[0].phase).toBe('intent')
    expect(ACT_DEFS[2].processTitle).toBe('证据核验')
    expect(ACT_DEFS[3].id).toBe('act4_attribution')
    expect(ACT_DEFS[3].processTitle).toBe('归因分析')
    expect(ACT_DEFS[6].id).toBe('act7_cases')
    expect(ACT_DEFS[6].processTitle).toBe('案例校验')
    expect(ACT_DEFS[8].reveal).toBe('plan')
    expect(ACT_DEFS[8].phase).toBe('plan')
    expect(ACT_DEFS.some((act) => act.processTitle === '方案确认与经验沉淀')).toBe(false)
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

  it('diagnosis acts include domain methodology lines', () => {
    const overflow = ACT_DEFS.find((a) => a.id === 'act3_overflow')!
    const text = narrationFor(overflow, fx).join('')
    expect(text).toContain('排队比')
    expect(text).toContain('饱和度')
    const strategy = ACT_DEFS.find((a) => a.id === 'act8_strategy')!
    expect(narrationFor(strategy, fx).join('')).toContain('治理路径')
  })

  it('attribution act summarizes primary cause; cases act omits narrative', () => {
    const attribution = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const cases = ACT_DEFS.find((item) => item.id === 'act7_cases')!
    const attributionText = narrationFor(attribution, fx).join('\n')
    const casesText = narrationFor(cases, fx).join('\n')
    const narrative = fx.phases?.cause?.cause_analysis?.narrative ?? ''
    const primary = fx.phases?.cause?.cause_analysis?.primary_cause ?? ''

    expect(attributionText).not.toContain('归因说明')
    if (narrative) expect(attributionText).not.toContain(narrative)
    expect(attributionText).toContain(primary)
    expect(summaryFor(attribution, fx)).toBe(primary)
    expect(casesText).toContain('案例校验')
    expect(casesText).not.toContain(primary)
  })

  it('uses saturation_rate when saturation is absent', () => {
    const response = {
      phases: {
        diagnosis: {
          metrics: {
            queue_ratio: 0.2,
            saturation_rate: 0.88,
            green_utilization: 0.57,
          },
        },
      },
      plan: null,
    } as unknown as RunResponse
    const act = ACT_DEFS.find((item) => item.id === 'act3_overflow')
    expect(act).toBeTruthy()

    expect(narrationFor(act!, response).join('')).toContain('0.88')
    expect(summaryFor(act!, response)).toContain('0.88')
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
