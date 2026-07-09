import { describe, expect, it, beforeEach } from 'vitest'
import {
  resetAbsorptionVoiceKeys,
  voiceCueForAbsorptionStage,
  voiceCueForAbsorptionStart,
} from '@/services/voiceAbsorptionSync'
import { ABSORPTION_STAGE_VOICE, ABSORPTION_VOICE_GUIDE } from '@/config/absorptionVoiceTemplates'

describe('voiceAbsorptionSync', () => {
  beforeEach(() => resetAbsorptionVoiceKeys())

  it('播报经验吸收开始与阶段文案', () => {
    const start = voiceCueForAbsorptionStart('run-1')
    expect(start?.text).toBe(ABSORPTION_VOICE_GUIDE.absorptionStart)
    expect(voiceCueForAbsorptionStart('run-1')).toBeNull()

    const recap = voiceCueForAbsorptionStage('run-1', 'recap')
    expect(recap?.text).toBe(ABSORPTION_STAGE_VOICE.recap)
    expect(voiceCueForAbsorptionStage('run-1', 'decompose')).toBeNull()
  })
})
