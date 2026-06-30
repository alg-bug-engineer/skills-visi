import { describe, expect, it } from 'vitest'
import { buildSuggestionPlainText } from './channelizationCopy'
import type { FlowTimingGovernance } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'

describe('buildSuggestionPlainText', () => {
  it('strips duplicated primary diagnosis headline from narrative', () => {
    const headline =
      '东左转已过饱和（饱和1.83、绿灯利用1.84），而西直行绿灯利用率0.35仍有富余——属于绿灯分配不均，配时可改善'
    const suggestion: GovernanceSuggestionPayload = {
      narrative: `${headline}。建议从西直行向东左转挪绿约 12 秒。`,
      delta_seconds: 12,
      direction: 'reallocate',
    }
    const governance: FlowTimingGovernance = {
      match_verdict: 'mismatch',
      primary_diagnosis: {
        type: 'timing_optimizable',
        headline,
        lever: '',
        severity: 'high',
        evidence: [],
        structure_limited: false,
      },
    }
    const text = buildSuggestionPlainText(suggestion, governance)
    expect(text).not.toContain(headline)
    expect(text).toContain('挪绿约 12 秒')
  })

  it('returns narrative text without duplicated headline', () => {
    const text = buildSuggestionPlainText(
      { narrative: '建议加绿。', delta_seconds: 8, direction: 'increase' },
      { match_verdict: 'mismatch', primary_diagnosis: { type: 'timing_optimizable', headline: '', lever: '', severity: 'medium', evidence: [], structure_limited: false } },
    )
    expect(text).toBe('建议加绿。')
  })
})
