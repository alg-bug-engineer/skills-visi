import { describe, expect, it } from 'vitest'
import { formatUpstreamTurnSplit } from './upstreamTurnSplit'

describe('formatUpstreamTurnSplit', () => {
  it('formats left/straight/right shares in fixed order', () => {
    const text = formatUpstreamTurnSplit([
      { turn: '直行', share_pct: 67 },
      { turn: '左转', share_pct: 22 },
      { turn: '右转', share_pct: 11 },
    ])
    expect(text).toBe('左转22% · 直行67% · 右转11%')
  })

  it('omits turns without share_pct or with data_gap', () => {
    const text = formatUpstreamTurnSplit([
      { turn: '直行', share_pct: 80 },
      { turn: '左转', data_gap: true },
      { turn: '右转', share_pct: null },
    ])
    expect(text).toBe('直行80%')
  })

  it('returns empty when no usable data', () => {
    expect(formatUpstreamTurnSplit([])).toBe('')
    expect(formatUpstreamTurnSplit(undefined)).toBe('')
    expect(
      formatUpstreamTurnSplit([{ turn: '左转', data_gap: true, share_pct: null }]),
    ).toBe('')
  })
})
