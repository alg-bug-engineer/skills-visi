import { onUnmounted, ref, type Ref } from 'vue'
import type { AnalysisQueue } from '../utils/analysisQueue'

export interface VoiceDrainControl {
  pauseDrain: () => void
  resumeDrain: () => void
}

export function usePresentationPause(
  analysisQueue: AnalysisQueue,
  voice?: VoiceDrainControl,
) {
  const paused = ref(false)

  function pause() {
    if (paused.value) return
    paused.value = true
    analysisQueue.pause()
    voice?.pauseDrain()
  }

  function resume() {
    if (!paused.value) return
    paused.value = false
    analysisQueue.resume()
    voice?.resumeDrain()
  }

  function toggle() {
    if (paused.value) resume()
    else pause()
  }

  function reset() {
    paused.value = false
    analysisQueue.resume()
    voice?.resumeDrain()
  }

  function bindSpaceKey(
    getActive: () => boolean = () => true,
    allowOnFocusedTextarea: () => boolean = () => false,
  ) {
    const onKeydown = (event: KeyboardEvent) => {
      if (event.code !== 'Space' && event.key !== ' ') return
      const target = event.target
      const onTextInput =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      if (onTextInput && !allowOnFocusedTextarea()) return
      if (!getActive()) return
      event.preventDefault()
      toggle()
    }
    window.addEventListener('keydown', onKeydown)
    return () => window.removeEventListener('keydown', onKeydown)
  }

  return { paused, pause, resume, toggle, reset, bindSpaceKey }
}

export function usePresentationPauseBinding(
  pause: ReturnType<typeof usePresentationPause>,
  getActive: () => boolean,
): void {
  let unbind: (() => void) | null = null
  unbind = pause.bindSpaceKey(getActive)
  onUnmounted(() => {
    unbind?.()
    unbind = null
  })
}

export type PresentationPauseState = Ref<boolean>
