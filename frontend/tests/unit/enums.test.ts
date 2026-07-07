import { describe, it, expect } from 'vitest'
import { t, directionMovement } from '@/labels/enums'

describe('enums', () => {
  it('translates known codes', () => {
    expect(t('direction', 'east_to_west')).toBe('东向西')
    expect(t('period', 'evening_peak')).toBe('晚高峰')
    expect(t('problem_type', 'queue_spillover')).toBe('排队溢出')
    expect(t('problem_type', 'congestion_spillover')).toBe('拥堵外溢')
    expect(t('constraint', 'avoid_downstream_spillover')).toBe('优先避免下游继续外溢')
    expect(t('plan_id', 'plan_dp')).toBe('干线联控方案')
  })
  it('falls back to raw value for unknown codes (F-01)', () => {
    expect(t('direction', 'diagonal_xyz')).toBe('diagonal_xyz')
  })
  it('handles null/empty', () => {
    expect(t('direction', null)).toBe('—')
    expect(t('direction', '')).toBe('—')
  })
  it('directionMovement combines', () => {
    expect(directionMovement('east_to_west', 'straight')).toBe('东向西直行')
    expect(directionMovement(null, null)).toBe('—')
  })
})
