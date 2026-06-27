import { describe, expect, it } from 'vitest'
import { buildEvidenceVoiceCue, buildImbalanceCue, buildSaturationCue } from './voiceCueExtractors'

describe('voiceCueExtractors', () => {
  it('prefers chronic highlight for evidence', () => {
    const cue = buildEvidenceVoiceCue({
      chronic: { is_chronic: true, congested_days: 5, window_days: 7 },
    })
    expect(cue.text).toContain('5 天常发拥堵')
    expect(cue.kind).toBe('highlight')
  })

  it('builds saturation cue', () => {
    const cue = buildSaturationCue(0.88)
    expect(cue?.text).toContain('百分之88')
    expect(cue?.text).toContain('过饱和')
  })

  it('builds imbalance cue', () => {
    const cue = buildImbalanceCue(0.42, 0.78)
    expect(cue?.text).toContain('失衡系数')
    expect(cue?.text).toContain('差异明显')
  })
})
