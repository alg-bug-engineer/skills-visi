import { describe, expect, it } from 'vitest'
import { buildEvidenceIntroCue, buildImbalanceCue, buildSaturationCue } from './voiceCueExtractors'
import { voiceConfig } from './voiceConfig'

describe('voiceCueExtractors', () => {
  it('uses stage guide for evidence intro', () => {
    const cue = buildEvidenceIntroCue()
    expect(cue.text).toBe(voiceConfig.guide.evidenceIntro)
    expect(cue.stepIndex).toBe(4)
  })

  it('builds saturation template cue', () => {
    const cue = buildSaturationCue(0.88)
    expect(cue?.text).toContain('0.88')
    expect(cue?.text).toContain('过饱和')
  })

  it('builds imbalance cue', () => {
    const cue = buildImbalanceCue(0.42, 0.78)
    expect(cue?.text).toContain('失衡系数')
    expect(cue?.text).toContain('差异明显')
  })
})
