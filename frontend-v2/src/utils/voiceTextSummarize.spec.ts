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

  it('traffic: speaks delay only, not saturation (saturation uses dedicated cue)', () => {
    const out = summarizeNarrationForVoice('traffic', '晚高峰整体饱和度1.50；延误指数1.89。')
    expect(out).toContain('1.89')
    expect(out).not.toContain('1.50')
  })

  it('granularity: turn label without saturation value', () => {
    const out = summarizeNarrationForVoice(
      'granularity',
      '转向级：东左转 饱和度 1.50；进口级：4 条进口道已纳入评价',
      '多粒度画像',
    )
    expect(out).toContain('东左转')
    expect(out).not.toContain('1.50')
  })

  it('saturation phase defers to buildSaturationCue', () => {
    const out = summarizeNarrationForVoice('saturation', '路口饱和度 1.50，已达过饱和。')
    expect(out).toBe('')
  })
})
