import type { Ref } from 'vue'
import type { ExperienceAbsorptionState } from '../types/skillAbsorption'

export interface PresentationBarrierDeps {
  whenProcessIdle: () => Promise<void>
  voice: {
    enabled: Ref<boolean>
    whenIdle: () => Promise<void>
  }
  getAbsorptionState: () => ExperienceAbsorptionState
}

/** 理解过程打字、TTS、经验吸收三条流均完成后才放行下一步。 */
export function createPresentationBarrier(deps: PresentationBarrierDeps) {
  function whenAbsorptionIdle(): Promise<void> {
    return new Promise((resolve) => {
      const tick = () => {
        const state = deps.getAbsorptionState()
        if (!state.active || state.currentStage === 'done') {
          resolve()
          return
        }
        const busy = state.lines.some((line) => line.status === 'running')
        if (!busy) resolve()
        else window.setTimeout(tick, 50)
      }
      tick()
    })
  }

  async function whenVoiceIdle(): Promise<void> {
    if (!deps.voice.enabled.value) return
    await deps.voice.whenIdle()
  }

  /** 步骤切换栅栏：任一呈现流未完成则阻塞 AnalysisQueue 下一步。 */
  async function whenSettled(): Promise<void> {
    await Promise.all([deps.whenProcessIdle(), whenVoiceIdle(), whenAbsorptionIdle()])
  }

  return { whenSettled, whenAbsorptionIdle, whenVoiceIdle }
}
