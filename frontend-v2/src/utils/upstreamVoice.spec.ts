import { describe, expect, it } from 'vitest'
import { shouldVoiceUpstreamFrame, summarizeUpstreamVoice } from './upstreamVoice'

describe('upstreamVoice', () => {
  it('voices approach intro, upstream nodes, and summary only', () => {
    expect(shouldVoiceUpstreamFrame('西进口过饱和，沿干线向上游追溯来车。')).toBe(true)
    expect(
      shouldVoiceUpstreamFrame('上游经十路与龙奥北路路口：饱和1.21，汇入车流 左转45%'),
    ).toBe(true)
    expect(shouldVoiceUpstreamFrame('西进口共溯 2 个上游路口，定位 1 个治理落点。')).toBe(false)
    expect(shouldVoiceUpstreamFrame('')).toBe(false)
  })

  it('summarizes to core conclusion', () => {
    expect(summarizeUpstreamVoice('西进口过饱和，沿干线向上游追溯来车。')).toContain('西进口')
    expect(summarizeUpstreamVoice('上游奥体西路与经十路路口：饱和0.73（仍偏饱和，继续上溯）')).toBe(
      '奥体西路与经十路路口，饱和度0.73。',
    )
    expect(summarizeUpstreamVoice('西进口共溯 1 个上游路口，定位 1 个治理落点。')).toContain(
      '共溯',
    )
  })

  it('summarizes over-saturated upstream without governable space', () => {
    expect(
      summarizeUpstreamVoice(
        '上游奥体西路与经十路路口：饱和0.95（上游亦过饱和，单点信控优化空间有限）',
      ),
    ).toContain('单点信控优化空间有限')
  })
})
