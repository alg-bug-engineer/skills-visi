import {
  ABSORPTION_STAGE_VOICE,
  ABSORPTION_VOICE_GUIDE,
} from '@/config/voiceTemplates'
import type { VoiceCue } from '@/types/voice'

const SOLIDIFY_STEP_INDEX = 9
const spokenAbsorptionKeys = new Set<string>()

export function resetAbsorptionVoiceKeys() {
  spokenAbsorptionKeys.clear()
}

function buildCue(runKey: string, phase: string, text: string, kind: VoiceCue['kind']): VoiceCue {
  return {
    id: `${runKey}:absorption:${phase}`,
    stepIndex: SOLIDIFY_STEP_INDEX,
    phase: `absorption:${phase}`,
    kind,
    text,
    priority: 0,
  }
}

export function voiceCueForAbsorptionStart(runKey: string): VoiceCue | null {
  const phase = 'start'
  const key = `${runKey}:${phase}`
  if (spokenAbsorptionKeys.has(key)) return null
  spokenAbsorptionKeys.add(key)
  return buildCue(runKey, phase, ABSORPTION_VOICE_GUIDE.absorptionStart, 'transition')
}

export function voiceCueForAbsorptionStage(runKey: string, stageKey: string): VoiceCue | null {
  const text = ABSORPTION_STAGE_VOICE[stageKey]
  if (!text) return null
  const key = `${runKey}:stage:${stageKey}`
  if (spokenAbsorptionKeys.has(key)) return null
  spokenAbsorptionKeys.add(key)
  return buildCue(runKey, stageKey, text, 'guide')
}

export function voiceCueForAbsorptionDone(runKey: string): VoiceCue | null {
  const phase = 'done'
  const key = `${runKey}:${phase}`
  if (spokenAbsorptionKeys.has(key)) return null
  spokenAbsorptionKeys.add(key)
  return buildCue(runKey, phase, ABSORPTION_VOICE_GUIDE.absorptionDone, 'transition')
}
