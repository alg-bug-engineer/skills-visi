import { describe, expect, it } from 'vitest'
import { shouldVoiceUpstreamFrame, summarizeUpstreamVoice } from './upstreamVoice'

describe('upstreamVoice', () => {
  it('voices upstream node facts only', () => {
    expect(shouldVoiceUpstreamFrame('上游经十路与龙奥北路路口：饱和1.21，汇入车流 左转45%')).toBe(
      true,
    )
    expect(shouldVoiceUpstreamFrame('西进口过饱和，沿干线向上游追溯来车。')).toBe(false)
    expect(shouldVoiceUpstreamFrame('西进口共溯 2 个上游路口，定位 1 个治理落点。')).toBe(false)
    expect(
      shouldVoiceUpstreamFrame('上游普遍过饱和，单点信控优化空间有限。'),
    ).toBe(false)
    expect(shouldVoiceUpstreamFrame('')).toBe(false)
  })

  it('summarizes upstream intersection without conclusion tail', () => {
    expect(summarizeUpstreamVoice('上游奥体西路与经十路路口：饱和0.73（仍偏饱和，继续上溯）')).toBe(
      '奥体西路与经十路路口，饱和度 0.73。',
    )
    expect(
      summarizeUpstreamVoice(
        '上游奥体西路与经十路路口：饱和0.95（上游亦过饱和，单点信控优化空间有限）',
      ),
    ).toBe('奥体西路与经十路路口，饱和度 0.95。')
    expect(summarizeUpstreamVoice('西进口过饱和，沿干线向上游追溯来车。')).toBe('')
  })
})
