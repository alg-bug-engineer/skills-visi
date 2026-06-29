import { describe, expect, it } from 'vitest'
import {
  BAND_COLORS,
  NO_DATA_COLOR,
  bandColor,
  isOversaturated,
  legendFor,
  metricColor,
  recordColor,
  saturationColor,
} from './scanColors'
import type { ScanRecord } from '../types/scan'

function rec(partial: Partial<ScanRecord>): ScanRecord {
  return {
    inter_id: 'X',
    inter_name: 'X',
    lon: 117,
    lat: 36,
    period: '早高峰',
    metrics: { saturation_max: 0.7, unbalance_index: 0.2, green_utilization: 0.6 },
    top_issues: [],
    severity: 'none',
    control_improvement_ceiling: 'medium',
    governance_summary: '',
    governance_actions: [],
    has_data: true,
    data_quality_tags: [],
    problem_band: '配时可解',
    pilot_score: 50,
    ...partial,
  }
}

describe('bandColor', () => {
  it('maps each band to its palette color', () => {
    expect(bandColor('配时可解')).toBe(BAND_COLORS['配时可解'])
    expect(bandColor('工程可解')).toBe(BAND_COLORS['工程可解'])
    expect(bandColor('无明显问题')).toBe(BAND_COLORS['无明显问题'])
    expect(bandColor('数据不足')).toBe(NO_DATA_COLOR)
  })
  it('falls back to no-data color for unknown band', () => {
    expect(bandColor('??')).toBe(NO_DATA_COLOR)
    expect(bandColor(null)).toBe(NO_DATA_COLOR)
  })
})

describe('saturationColor', () => {
  it('ramps green -> red and is red at oversaturation', () => {
    expect(saturationColor(0.4)).toBe('#27ae60')
    expect(saturationColor(0.7)).toBe('#f1c40f')
    expect(saturationColor(0.85)).toBe('#e67e22')
    expect(saturationColor(1.2)).toBe('#c0392b')
  })
  it('returns no-data color for null/NaN', () => {
    expect(saturationColor(null)).toBe(NO_DATA_COLOR)
    expect(saturationColor(undefined)).toBe(NO_DATA_COLOR)
    expect(saturationColor(NaN)).toBe(NO_DATA_COLOR)
  })
})

describe('metricColor', () => {
  it('green utilization is red when low', () => {
    expect(metricColor('green_utilization', 0.3)).toBe('#c0392b')
    expect(metricColor('green_utilization', 0.9)).toBe('#27ae60')
  })
})

describe('recordColor', () => {
  it('uses no-data color when record lacks data regardless of mode', () => {
    expect(recordColor(rec({ has_data: false }), 'band')).toBe(NO_DATA_COLOR)
    expect(recordColor(rec({ has_data: false }), 'saturation_max')).toBe(NO_DATA_COLOR)
  })
  it('colors by band or metric', () => {
    expect(recordColor(rec({ problem_band: '工程可解' }), 'band')).toBe(BAND_COLORS['工程可解'])
    expect(
      recordColor(rec({ metrics: { saturation_max: 1.1, unbalance_index: 0, green_utilization: 0 } }), 'saturation_max'),
    ).toBe('#c0392b')
  })
})

describe('isOversaturated', () => {
  it('flags >= 0.9', () => {
    expect(isOversaturated(rec({ metrics: { saturation_max: 1.05, unbalance_index: 0, green_utilization: 0 } }))).toBe(true)
    expect(isOversaturated(rec({ metrics: { saturation_max: 0.7, unbalance_index: 0, green_utilization: 0 } }))).toBe(false)
  })
})

describe('legendFor', () => {
  it('band legend includes pilot-first and engineering-invalid labels', () => {
    const labels = legendFor('band').map((l) => l.label)
    expect(labels.some((l) => l.includes('试点首选'))).toBe(true)
    expect(labels.some((l) => l.includes('配时无效'))).toBe(true)
  })
})
