export type VoiceCueKind = 'guide' | 'transition'

export interface VoiceCue {
  id: string
  stepIndex: number
  phase: string
  kind: VoiceCueKind
  text: string
  priority: 0 | 1 | 2
}
