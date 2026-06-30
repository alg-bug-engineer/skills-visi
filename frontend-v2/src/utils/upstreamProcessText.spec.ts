import { describe, expect, it } from 'vitest'
import { buildUpstreamProcessText } from './upstreamProcessText'
import type { UpstreamStoryboard } from '../types/map'

const SB: UpstreamStoryboard = {
  trees: [
    {
      tree_id: 'N',
      approach: '北进口',
      nodes: [
        { id: 'T', role: 'target', name: '目标' },
        { id: 'U1', role: 'upstream', name: '经十路路口', hop: 1, saturation: 0.73 },
        { id: 'A', role: 'governance', name: '龙奥北路路口', hop: 2, saturation: 0.95 },
      ],
      edges: [],
    },
  ],
  frames: [],
}

describe('buildUpstreamProcessText', () => {
  it('lists upstream chain per approach without governance verdict', () => {
    const text = buildUpstreamProcessText(SB)
    expect(text).toContain('流量溯源')
    expect(text).toContain('北进口')
    expect(text).toContain('经十路路口（饱和 0.73）')
    expect(text).toContain('龙奥北路路口（饱和 0.95）')
    expect(text).not.toContain('治理落点')
  })

  it('numbers each upstream hop', () => {
    const text = buildUpstreamProcessText(SB)
    expect(text).toContain('上游1 经十路路口')
    expect(text).toContain('上游2 龙奥北路路口')
  })

  it('uses provided target turn label as the headline', () => {
    const text = buildUpstreamProcessText(SB, '西左转')
    expect(text).toContain('西左转 沿干线追溯上游来车。')
    expect(text).toContain('西左转 → 上游1 经十路路口')
  })

  it('returns empty for missing storyboard', () => {
    expect(buildUpstreamProcessText(null)).toBe('')
  })
})
