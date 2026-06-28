import { describe, expect, it } from 'vitest'
import { ANALYSIS_STEP_LABELS, STEP_INDICES, THRESHOLDS } from '../constants'
import {
  constraintProgress,
  formatPercent,
  formatSaturation,
  highlightDirsForGroup,
  metricLabel,
  sourceTierLabel,
} from '../utils/evidencePresentation'
import { createInitialPresentation } from '../types/presentation'

describe('constants', () => {
  it('has 8 analysis steps including problem evidence', () => {
    expect(ANALYSIS_STEP_LABELS).toHaveLength(8)
    expect(ANALYSIS_STEP_LABELS[STEP_INDICES.PROBLEM_EVIDENCE]).toBe('问题印证')
  })

  it('aligns thresholds with backend yaml', () => {
    expect(THRESHOLDS.saturationHigh).toBe(0.8)
    expect(THRESHOLDS.spillbackRiskHigh).toBe(0.8)
  })
})

describe('evidencePresentation', () => {
  it('formats percent values', () => {
    expect(formatPercent(0.92)).toBe('92%')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats saturation as decimal ratio', () => {
    expect(formatSaturation(0.92)).toBe('0.92')
    expect(formatSaturation(1.5)).toBe('1.50')
    expect(formatSaturation(null)).toBe('—')
  })

  it('maps metric labels', () => {
    expect(metricLabel('spillback_risk')).toBe('溢流风险')
  })

  it('maps source tier labels', () => {
    expect(sourceTierLabel('dwd_rolling_7d')).toBe('近7日明细')
    expect(sourceTierLabel('mock')).toBe('演示数据')
  })

  it('expands direction groups to highlight dirs', () => {
    expect(highlightDirsForGroup('东西向')).toEqual(['东', '西'])
  })

  it('computes constraint progress', () => {
    const p = constraintProgress({
      metric: 'spillback_risk',
      scope: '南北向',
      operator: '<=',
      value: 0.47,
      baseline: 0.42,
    })
    expect(p.baseline).toBe(0.42)
    expect(p.cap).toBe(0.47)
  })
})

describe('presentation state', () => {
  it('creates idle initial state', () => {
    const s = createInitialPresentation()
    expect(s.phase).toBe('idle')
    expect(s.evidence).toBeNull()
    expect(s.insightCards).toEqual([])
    expect(s.dataInsightBuffer).toBeNull()
    expect(s.revealedInsightSteps).toEqual({
      data: false,
      evidence: false,
      constraints: false,
      extended: false,
      governance: false,
      suggestionNote: false,
    })
  })
})
