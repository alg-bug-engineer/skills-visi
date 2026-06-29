/**
 * 语音播报文案 — 从 config/voice_narration.json 加载。
 * 文案为固定模板 + 运行时数据填充，TTS 仅负责合成，不由大模型生成旁白。
 */
import raw from '../config/voice_narration.json'

export interface VoiceNarrationConfig {
  guide: Record<string, string>
  absorption: Record<string, string>
  templates: Record<string, string>
  states: Record<string, string>
  direction: Record<string, string>
  playback: {
    cueGapMs: number
    drainTailMs: number
    interruptOnHighPriority: boolean
    intersectionGuideGapMs?: number
  }
}

export const voiceConfig = raw as VoiceNarrationConfig

export function voiceGuide(key: keyof VoiceNarrationConfig['guide'] | string): string {
  return voiceConfig.guide[key] ?? ''
}

export function voiceAbsorption(stage: string): string | undefined {
  return voiceConfig.absorption[stage]
}

export function voiceTemplate(
  key: keyof VoiceNarrationConfig['templates'] | string,
  vars: Record<string, string | number>,
): string {
  let text = voiceConfig.templates[key] ?? ''
  for (const [name, value] of Object.entries(vars)) {
    text = text.replace(new RegExp(`\\{${name}\\}`, 'g'), String(value))
  }
  return text
}

export function saturationStateLabel(saturation: number): string {
  if (saturation >= 0.85) return voiceConfig.states.saturationOversat
  if (saturation >= 0.65) return voiceConfig.states.saturationElevated
  return voiceConfig.states.saturationNormal
}

export function imbalanceTailLabel(imbalance: number): string {
  return imbalance >= 0.3
    ? voiceConfig.states.imbalanceUneven
    : voiceConfig.states.imbalanceEven
}

/** @deprecated 使用 voiceGuide / voiceTemplate；保留兼容旧 import */
export const VOICE_GUIDE = {
  understand: voiceConfig.guide.understand,
  intersection: (name: string) => voiceTemplate('intersection', { name }),
  cognition: voiceConfig.guide.cognition,
  dataFetch: voiceConfig.guide.dataFetch,
  evidenceIntro: voiceConfig.guide.evidenceIntro,
  ruleIntro: voiceConfig.guide.ruleIntro,
  suggestionConfirm: voiceConfig.guide.suggestionConfirm,
  absorptionStart: voiceConfig.guide.absorptionStart,
  absorptionDone: voiceConfig.guide.absorptionDone,
  skillBuildStart: voiceConfig.guide.skillBuildStart,
  skillBuildDone: voiceConfig.guide.skillBuildDone,
} as const

export const ABSORPTION_STAGE_VOICE: Record<string, string> = voiceConfig.absorption
