import { describe, expect, it } from 'vitest'
import { ticketTimeLabel, ticketLocationLine, ticketPrimaryConstraint, ticketConstraintList } from '@/utils/ticketCopy'

describe('ticketCopy', () => {
  it('shows period only when time_range is missing', () => {
    expect(
      ticketTimeLabel({
        period: 'morning_peak',
      } as never),
    ).toBe('早高峰')
  })

  it('prefers intersection name over redundant object type line', () => {
    expect(
      ticketLocationLine({
        object_type: 'intersection',
        intersection_name: '解放东路与奥体中路路口',
      } as never),
    ).toBe('已识别路口：解放东路与奥体中路路口')
  })

  it('reads string constraints as a whole phrase', () => {
    expect(
      ticketPrimaryConstraint({
        constraints: '优先避免下游继续外溢',
      } as never),
    ).toBe('优先避免下游继续外溢')
  })

  it('hides internal methodology constraints from ticket display', () => {
    expect(
      ticketConstraintList({
        constraints:
          '按跨周峰值核验；下游永绥路与齐音路北进口直行按跨周均值评估承接并披露峰值风险；采用目标峰值日现状配时和可用流量',
      } as never),
    ).toEqual([])
    expect(
      ticketPrimaryConstraint({
        constraints:
          '按跨周峰值核验；下游永绥路与齐音路北进口直行按跨周均值评估承接并披露峰值风险；采用目标峰值日现状配时和可用流量',
      } as never),
    ).toBeNull()
  })
})
