import { describe, expect, it } from 'vitest'
import { ANALYSIS_STEP_LABELS, STEP_INDICES } from '../constants'
import { voiceConfig } from './voiceConfig'
import {
  PROCESS_STEP_VOICE_MAP,
  resolveProcessStepVoice,
} from './voiceStepSync'

describe('voiceStepSync', () => {
  it('maps each core analysis step to voice_narration.json', () => {
    for (const row of PROCESS_STEP_VOICE_MAP) {
      expect(ANALYSIS_STEP_LABELS[row.index]).toBe(row.label)
      if (row.index === STEP_INDICES.INTERSECTION) {
        expect(voiceConfig.templates.intersection).toBeTruthy()
        continue
      }
      const guide = voiceConfig.guide[row.configKey as keyof typeof voiceConfig.guide]
      expect(guide, `${row.label} missing guide.${row.configKey}`).toBeTruthy()
    }
  })

  it('uses empty-green data fetch guide when problem type is empty_green', () => {
    expect(
      resolveProcessStepVoice(STEP_INDICES.DATA_FETCH, { problemTypes: ['empty_green'] }),
    ).toBe(voiceConfig.guide.dataFetchEmptyGreen)
  })

  it('returns stage guides aligned with understanding process labels', () => {
    expect(resolveProcessStepVoice(STEP_INDICES.UNDERSTAND)).toBe(voiceConfig.guide.understand)
    expect(resolveProcessStepVoice(STEP_INDICES.COGNITION)).toBeNull()
    expect(resolveProcessStepVoice(STEP_INDICES.DATA_FETCH)).toBe(voiceConfig.guide.dataFetch)
    expect(resolveProcessStepVoice(STEP_INDICES.PROBLEM_EVIDENCE)).toBe(
      voiceConfig.guide.evidenceIntro,
    )
    expect(resolveProcessStepVoice(STEP_INDICES.RULE)).toBe(voiceConfig.guide.ruleIntro)
    expect(resolveProcessStepVoice(STEP_INDICES.SUGGESTION)).toBe(
      voiceConfig.guide.suggestionConfirm,
    )
  })

  it('intersection voice requires matched intersection name', () => {
    expect(resolveProcessStepVoice(STEP_INDICES.INTERSECTION)).toBeNull()
    expect(
      resolveProcessStepVoice(STEP_INDICES.INTERSECTION, { intersectionName: '奥体西路经十路' }),
    ).toContain('奥体西路经十路')
  })

  it('does not emit voice for skill solidification step index', () => {
    expect(resolveProcessStepVoice(STEP_INDICES.SKILL)).toBeNull()
  })
})
