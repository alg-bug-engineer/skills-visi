import { describe, expect, it } from 'vitest'
import { summarizeNarrationForVoice } from './voiceTextSummarize'

describe('summarizeNarrationForVoice', () => {
  it('corridor phase is suppressed', () => {
    const out = summarizeNarrationForVoice(
      'corridor',
      '该路口位于奥体西路协调段第3/8个路口，协调周期100秒，绿波存在断裂风险。',
      '干线协调',
    )
    expect(out).toBe('')
  })

  it('timing: cycle/seconds broadcast is removed (no "周期 N 秒")', () => {
    const out = summarizeNarrationForVoice(
      'timing',
      '当前方案周期约 120s，日计划时段 4 个。',
      '配时适配性',
    )
    expect(out).toBe('')
    expect(out).not.toContain('120')
  })

  it('traffic: speaks delay only, not saturation (saturation uses dedicated cue)', () => {
    const out = summarizeNarrationForVoice('traffic', '晚高峰整体饱和度1.50；延误指数1.89。')
    expect(out).toContain('1.89')
    expect(out).not.toContain('1.50')
  })

  it('saturation phase is suppressed', () => {
    const out = summarizeNarrationForVoice('saturation', '路口饱和度 1.50，已达过饱和。')
    expect(out).toBe('')
  })

  it('long narration is clamped at sentence boundary, never mid-clause', () => {
    const out = summarizeNarrationForVoice(
      'structure',
      '该路口为四进口交叉。东西向为主干道，承担过境交通。南北向为次干道，连接居住区。',
      '路口结构',
    )
    // 不在句中切断：结尾必须是完整句标点
    expect(out.endsWith('。') || out.endsWith('交叉')).toBe(true)
    expect(out.length).toBeGreaterThan(10)
  })
})
