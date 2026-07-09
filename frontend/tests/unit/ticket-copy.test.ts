import { describe, expect, it } from 'vitest'
import { ticketTimeLabel, ticketLocationLine, ticketPrimaryConstraint } from '@/utils/ticketCopy'
import { narrationFor, ACT_DEFS } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'

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

describe('narrationFor act1_ticket', () => {
  it('does not repeat 路口 or show em dash time placeholder', () => {
    const act = ACT_DEFS[0]
    const resp = {
      diagnosis_ticket: {
        object_type: 'intersection',
        intersection_name: '解放东路与奥体中路路口',
        period: 'morning_peak',
        direction: 'south_to_north',
        movement: 'straight',
        problem_type: 'congestion',
        constraints: '优先避免下游继续外溢',
      },
      phases: {},
      plan: null,
    } as unknown as RunResponse

    const lines = narrationFor(act, resp)
    expect(lines.join('\n')).toContain('已识别路口：解放东路与奥体中路路口')
    expect(lines.join('\n')).not.toContain('对象：路口')
    expect(lines.join('\n')).toContain('时段：早高峰')
    expect(lines.join('\n')).not.toContain('—（早高峰）')
    expect(lines.join('\n')).toContain('关键约束：优先避免下游继续外溢')
    expect(lines.every((line) => line.trim().length > 0)).toBe(true)
  })
})
