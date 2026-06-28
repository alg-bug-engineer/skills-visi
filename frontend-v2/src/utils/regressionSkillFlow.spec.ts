import { describe, expect, it } from 'vitest'
import {
  shouldEnqueueAbsorptionVoice,
  shouldEnqueueSkillBuildVoice,
  shouldShowSkillSolidificationStep,
} from './regressionSkillFlow'

describe('regressionSkillFlow RT-UI-07 / RT-VOICE-16', () => {
  it('reused_no_persist does not show skill solidification step', () => {
    expect(shouldShowSkillSolidificationStep('reused_no_persist', 'done')).toBe(false)
  })

  it('skipped_no_user_suggestion does not show skill solidification step', () => {
    expect(shouldShowSkillSolidificationStep('skipped_no_user_suggestion', 'done')).toBe(false)
  })

  it('awaiting_create shows skill solidification step', () => {
    expect(shouldShowSkillSolidificationStep('awaiting_create', 'awaiting_confirm')).toBe(true)
  })

  it('skill_created shows skill solidification step', () => {
    expect(shouldShowSkillSolidificationStep('created', 'done')).toBe(true)
  })

  it('no absorption voice without skill_absorption events', () => {
    expect(shouldEnqueueAbsorptionVoice('skill_build_start')).toBe(false)
    expect(shouldEnqueueAbsorptionVoice('step')).toBe(false)
  })

  it('absorption voice only on skill_absorption event types', () => {
    expect(shouldEnqueueAbsorptionVoice('skill_absorption_start')).toBe(true)
    expect(shouldEnqueueAbsorptionVoice('stage_start')).toBe(true)
    expect(shouldEnqueueAbsorptionVoice('skill_absorption_done')).toBe(true)
  })

  it('skill build voice on build events only', () => {
    expect(shouldEnqueueSkillBuildVoice('skill_build_start')).toBe(true)
    expect(shouldEnqueueSkillBuildVoice('skill_build_done')).toBe(true)
    expect(shouldEnqueueSkillBuildVoice('skill_absorption_start')).toBe(false)
  })
})
