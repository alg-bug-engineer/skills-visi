import { describe, expect, it } from 'vitest'
import {
  buildCognitionVoiceCue,
  buildDirectionVoiceCue,
  buildEvidenceIntroCue,
  buildImbalanceCue,
  buildNarrationPhaseVoiceCue,
  buildSaturationCue,
} from './voiceCueExtractors'
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

  it('RT-VOICE-AXIS: builds cognition cue from axis roads', () => {
    const cue = buildCognitionVoiceCue({
      axis_roads: { 东西向: '经十路', 南北向: '奥体西路' },
      intersectionName: '经十路与奥体西路路口',
    })
    expect(cue?.text).toContain('东西向为经十路')
    expect(cue?.text).toContain('南北向为奥体西路')
  })

  it('builds corridor narration cue with key points only', () => {
    const cue = buildNarrationPhaseVoiceCue(
      'corridor',
      '该路口位于奥体西路协调段第3/8个路口，协调周期100秒，绿波存在断裂风险。',
      '干线协调',
    )
    expect(cue?.text).toContain('奥体西路')
    expect(cue?.text).not.toContain('协调周期100秒')
    expect(cue?.phase).toBe('corridor')
  })

  it('builds direction role cue for focus and protect', () => {
    const cue = buildDirectionVoiceCue([
      { group: '南北向', role: 'focus', saturation: 0.92 },
      { group: '东西向', role: 'protect', saturation: 0.61 },
    ])
    expect(cue?.text).toContain('关注南北向')
    expect(cue?.text).toContain('东西向为保护方向')
  })
})
