import { describe, expect, it } from 'vitest'
import { buildSuggestionPlainText } from './channelizationCopy'
import type { FlowTimingGovernance } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'

describe('buildSuggestionPlainText', () => {
  it('uses action plan headline instead of zero-second increase line', () => {
    const suggestion: GovernanceSuggestionPayload = {
      narrative: '建议优化绿信比，将北左转部分时间调剂给东左转。',
      delta_seconds: 0,
      direction: 'reallocate',
    }
    const governance: FlowTimingGovernance = {
      match_verdict: 'mismatch',
      primary_diagnosis: { type: 'timing_optimizable', headline: '', lever: '', severity: 'high', evidence: [], structure_limited: false },
      action_plan: {
        action_type: 'reallocate_green',
        headline: '保持周期 120s，从北左转向东左转挪绿约 0s',
        transfer_seconds: 0,
      },
    }
    const text = buildSuggestionPlainText(suggestion, governance)
    expect(text).toContain('保持周期 120s')
    expect(text).not.toContain('增加主要方向绿灯约 0 秒')
  })

  it('keeps positive delta fallback when no plan headline', () => {
    const text = buildSuggestionPlainText(
      { narrative: '建议加绿。', delta_seconds: 8, direction: 'increase' },
      { match_verdict: 'mismatch', primary_diagnosis: { type: 'timing_optimizable', headline: '', lever: '', severity: 'medium', evidence: [], structure_limited: false } },
    )
    expect(text).toContain('增加主要方向绿灯约 8 秒')
  })
})
