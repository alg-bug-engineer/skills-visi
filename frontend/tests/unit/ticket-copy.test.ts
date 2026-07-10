import { describe, expect, it } from 'vitest'
import { ticketTimeLabel, ticketLocationLine, ticketPrimaryConstraint } from '@/utils/ticketCopy'

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
})
