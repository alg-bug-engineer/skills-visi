import { describe, expect, it } from 'vitest'
import { summarizeNarrationForVoice } from './voiceTextSummarize'

describe('summarizeNarrationForVoice', () => {
  it('corridor: extracts road and risk without full narrative', () => {
    const out = summarizeNarrationForVoice(
      'corridor',
      '该路口位于奥体西路协调段第3/8个路口，协调周期100秒，绿波存在断裂风险，需关注上下游相位。',
      '干线协调',
    )
    expect(out).toContain('干线')
    expect(out).toContain('奥体西路')
    expect(out).toContain('风险')
    expect(out.length).toBeLessThan(60)
  })

  it('timing: keeps cycle hint only', () => {
    const out = summarizeNarrationForVoice(
      'timing',
      '当前方案周期约 120s，日计划时段 4 个。',
      '配时适配性',
    )
    expect(out).toContain('120')
    expect(out).not.toContain('不匹配')
  })

  it('falls back to first clause', () => {
    const out = summarizeNarrationForVoice('traffic', '晚高峰整体饱和度1.50；延误指数1.89。')
    expect(out).toContain('1.50')
  })

  it('granularity: avoids duplicate 饱和度 in TTS', () => {
    const out = summarizeNarrationForVoice(
      'granularity',
      '转向级：东左转 饱和度 1.50；进口级：4 条进口道已纳入评价',
      '多粒度画像',
    )
    expect(out).toBe('东左转，1.50')
    expect(out).not.toMatch(/饱和度饱和度/)
  })
})
