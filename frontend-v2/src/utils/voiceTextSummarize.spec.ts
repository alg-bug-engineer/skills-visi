import { describe, expect, it } from 'vitest'
import { summarizeNarrationForVoice } from './voiceTextSummarize'

describe('summarizeNarrationForVoice · problem-type aware', () => {
  it('reads green utilization for empty_green traffic phase', () => {
    const spoken = summarizeNarrationForVoice(
      'traffic',
      '绿灯利用率 0.42，空放明显',
      null,
      60,
      ['empty_green'],
    )
    expect(spoken).toBe('绿灯利用率0.42')
  })

  it('reads delay for congestion traffic phase', () => {
    const spoken = summarizeNarrationForVoice(
      'traffic',
      '延误指数 1.47',
      null,
      60,
      ['congestion'],
    )
    expect(spoken).toBe('延误指数1.47')
  })
})
