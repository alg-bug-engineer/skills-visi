/** Short voice cue for guided narration (not full screen text). */

export type VoiceCueKind = 'guide' | 'highlight' | 'transition'

export interface VoiceCue {
  id: string
  stepIndex: number
  phase: string
  kind: VoiceCueKind
  text: string
  priority: 0 | 1 | 2
}

export { ABSORPTION_STAGE_VOICE } from '../services/voiceConfig'
