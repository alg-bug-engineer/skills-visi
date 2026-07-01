import { describe, expect, it } from 'vitest'
import { formatUpstreamTurnSplit, formatUpstreamTurnSplitHtml } from './upstreamTurnSplit'

describe('formatUpstreamTurnSplit', () => {
  it('formats directional movement shares by share_pct desc', () => {
    const text = formatUpstreamTurnSplit([
      { turn: '直行', feed_direction: '东直行', share_pct: 76.2 },
      { turn: '右转', feed_direction: '北右转', share_pct: 16.1 },
      { turn: '左转', feed_direction: '西左转', share_pct: 7.7 },
    ])
    expect(text).toBe('东直行76.2% · 北右转16.1% · 西左转7.7%')
  })

  it('falls back to turn when feed_direction missing', () => {
    const text = formatUpstreamTurnSplit([
      { turn: '直行', share_pct: 67 },
      { turn: '左转', share_pct: 22 },
      { turn: '右转', share_pct: 11 },
    ])
    expect(text).toBe('直行67% · 左转22% · 右转11%')
  })

  it('omits turns without share_pct or with data_gap', () => {
    const text = formatUpstreamTurnSplit([
      { turn: '直行', feed_direction: '东直行', share_pct: 80 },
      { turn: '左转', feed_direction: '北左转', data_gap: true },
      { turn: '右转', feed_direction: '南右转', share_pct: null },
    ])
    expect(text).toBe('东直行80%')
  })

  it('returns empty when no usable data', () => {
    expect(formatUpstreamTurnSplit([])).toBe('')
    expect(formatUpstreamTurnSplit(undefined)).toBe('')
    expect(
      formatUpstreamTurnSplit([{ turn: '左转', data_gap: true, share_pct: null }]),
    ).toBe('')
  })
})

describe('formatUpstreamTurnSplitHtml', () => {
  it('renders list rows with movement label and pct', () => {
    const html = formatUpstreamTurnSplitHtml([
      { turn: '直行', feed_direction: '东直行', share_pct: 76.2 },
      { turn: '右转', feed_direction: '北右转', share_pct: 16.1 },
    ])
    expect(html).toContain('us-split-item')
    expect(html).toContain('东直行')
    expect(html).toContain('76.2%')
    expect(html).toContain('北右转')
    expect(html).toContain('16.1%')
  })
})
