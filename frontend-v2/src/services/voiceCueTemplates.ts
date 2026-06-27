/** @deprecated 请直接修改 src/config/voice_narration.json 或从 voiceConfig 导入 */
export {
  ABSORPTION_STAGE_VOICE,
  VOICE_GUIDE,
  voiceConfig,
  voiceGuide,
  voiceTemplate,
} from './voiceConfig'

import { voiceConfig, voiceTemplate } from './voiceConfig'

export function voiceSaturation(saturation: number, state: string): string {
  return voiceTemplate('saturation', { value: saturation.toFixed(2), state })
}

export function voiceImbalance(imbalance: number, uneven: boolean): string {
  const tail = uneven ? voiceConfig.states.imbalanceUneven : voiceConfig.states.imbalanceEven
  return voiceTemplate('imbalance', { value: imbalance.toFixed(2), tail })
}

export function voiceSuggestion(direction: string | undefined, delta: number | undefined): string {
  if (delta == null) return voiceConfig.templates.suggestionFallback
  const dir =
    direction === 'increase' ? voiceConfig.direction.increase : voiceConfig.direction.decrease
  return voiceTemplate('suggestion', { direction: dir, delta: Math.abs(delta) })
}
