import { describe, expect, it } from 'vitest'
import type { FlowTrace } from '../types/evidence'
import { buildFlowTraceSummaryLines, formatEntryMovementBrief } from './flowTraceCopy'

const TRACE: FlowTrace = {
  available: true,
  caveat: 'near_month_pattern',
  entry_traces: [
    {
      entry: '东进口',
      dir8_code: 2,
      entry_max_saturation: 1.73,
      upstream_inter_id: 'U1',
      upstream_inter_name: '岔口',
      vehicles_base: 100,
      narrative:
        '东进口约100辆过境车中，约82辆来自上一路口岔口，以直行为主（82辆）',
      dominant_movement: {
        turn: '直行',
        cor_turn: 2,
        feed_direction: '东南进口直行',
        share_pct: 82,
        vehicles_of_100: 82,
        raw_coverage: 81.8,
      },
      upstream_movements: [
        {
          turn: '直行',
          cor_turn: 2,
          feed_direction: '东南进口直行',
          share_pct: 82,
          vehicles_of_100: 82,
          raw_coverage: 81.8,
        },
      ],
    },
  ],
}

describe('buildFlowTraceSummaryLines', () => {
  it('builds summary lines from entry_traces narratives', () => {
    const lines = buildFlowTraceSummaryLines(TRACE)
    expect(lines).toHaveLength(1)
    expect(lines[0].entry).toBe('东进口')
    expect(lines[0].text).toContain('100辆')
    expect(lines[0].text).toContain('岔口')
  })

  it('returns empty when unavailable', () => {
    expect(buildFlowTraceSummaryLines({ available: false })).toEqual([])
    expect(buildFlowTraceSummaryLines(null)).toEqual([])
  })
})

describe('formatEntryMovementBrief', () => {
  it('formats dominant movement as 辆/100', () => {
    const entry = TRACE.entry_traces![0]
    const brief = formatEntryMovementBrief(entry)
    expect(brief).toContain('东进口')
    expect(brief).toContain('岔口')
    expect(brief).toContain('82辆/100')
  })
})
