import { describe, it, expect } from 'vitest'
import { t, directionMovement, translatePlanId } from '@/labels/enums'

describe('enums', () => {
  it('translates known codes', () => {
    expect(t('direction', 'east_to_west')).toBe('东向西')
    expect(t('period', 'evening_peak')).toBe('晚高峰')
    expect(t('problem_type', 'queue_spillover')).toBe('排队溢出')
    expect(t('problem_type', 'congestion_spillover')).toBe('拥堵外溢')
    expect(t('constraint', 'avoid_downstream_spillover')).toBe('优先避免下游继续外溢')
    expect(t('plan_id', 'plan_dp')).toBe('干线联控方案')
  })

  it('translates plan and strategy package codes', () => {
    expect(t('plan_id', 'downstream_protection')).toBe('下游保护方案')
    expect(t('strategy_package', 'incremental_release')).toBe('目标路口小步释放')
    expect(t('bottleneck_type', 'downstream_or_channelization')).toBe('下游或渠化受限')
    expect(translatePlanId('arterial_coordination')).toBe('干线联控方案')
  })

  it('translates requirement-16 production enum codes', () => {
    expect(t('period', 'evening_rush_hour')).toBe('晚高峰')
    expect(t('problem_type', 'queue_overflow')).toBe('排队溢出')
    expect(t('diagnosis_scope', 'signal_timing_and_queue_management')).toBe('信号配时与排队管理')
    expect(t('governance_goal', 'clear_upstream_queue_and_isolate_downstream_impact')).toBe(
      '清空上游排队并隔离下游影响',
    )
  })

  it('humanizes unknown snake_case instead of exposing raw codes', () => {
    expect(t('direction', 'diagonal_xyz')).toBe('diagonal xyz')
    expect(t('problem_type', 'foo_bar_queue')).toContain('排队')
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
