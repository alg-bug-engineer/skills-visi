import { describe, expect, it } from 'vitest'
import { buildEvidenceListItems, buildSuggestionPlainText } from './channelizationCopy'
import type { FlowTimingGovernance, ProblemEvidence } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'

describe('buildEvidenceListItems', () => {
  it('filters congestion metrics when primary problem is conflict', () => {
    const evidence: ProblemEvidence = {
      problem_types: ['conflict'],
      diagnosis_story: [
        { phase: 'conflict_channel', title: '渠化匹配', text: '东进口存在左转与直行混行' },
        { phase: 'metrics', title: '运行状态', text: '饱和度 0.73，延误指数 0.84' },
        { phase: 'chronic', title: '常发性', text: '近7日中5日该时段运行指标超标' },
      ],
    }
    const items = buildEvidenceListItems(evidence)
    expect(items.some((i) => i.includes('渠化匹配'))).toBe(true)
    expect(items.some((i) => i.includes('饱和度'))).toBe(false)
    expect(items.some((i) => i.includes('常发性'))).toBe(false)
  })

  it('shows empty-green contrast beats instead of saturation metrics', () => {
    const evidence: ProblemEvidence = {
      problem_types: ['empty_green', 'congestion'],
      diagnosis_story: [
        { phase: 'empty_green_contrast', title: '空放对比', text: '西进口绿灯常无车放行，而东进口排队较长' },
        { phase: 'metrics', title: '运行状态', text: '饱和度 0.73' },
      ],
    }
    const items = buildEvidenceListItems(evidence)
    expect(items.some((i) => i.includes('空放对比'))).toBe(true)
    expect(items.some((i) => i.includes('饱和度'))).toBe(false)
  })
})

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
