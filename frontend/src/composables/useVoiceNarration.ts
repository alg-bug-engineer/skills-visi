import { ref, shallowRef } from 'vue'
import type { VoiceCue } from '@/types/voice'
import { synthesizeVoiceWav } from '@/services/ttsClient'

const STORAGE_KEY = 'voice-narration-enabled'
const CUE_GAP_MS = 280

function loadVoiceEnabled(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === null) {
    localStorage.setItem(STORAGE_KEY, '1')
    return true
  }
  return stored !== '0'
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function useVoiceNarration() {
  const enabled = ref(loadVoiceEnabled())
  const playing = ref(false)
  const queue = shallowRef<VoiceCue[]>([])
  let fallbackAudio: HTMLAudioElement | null = null
  let abortController: AbortController | null = null
  let drainPromise: Promise<void> | null = null
  let sessionEpoch = 0

  function stopPlayback() {
    abortController?.abort()
    abortController = null
    if (fallbackAudio) {
      fallbackAudio.pause()
      fallbackAudio.src = ''
      fallbackAudio = null
    }
    playing.value = false
  }

  function interrupt() {
    sessionEpoch += 1
    queue.value = []
    stopPlayback()
    drainPromise = null
  }

  function setEnabled(value: boolean) {
    enabled.value = value
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
    if (!value) interrupt()
  }

  function toggleEnabled() {
    setEnabled(!enabled.value)
  }

  function enqueue(cue: VoiceCue | null | undefined) {
    if (!cue || !enabled.value) return
    const rest = queue.value.filter((item) => item.stepIndex !== cue.stepIndex || item.phase !== cue.phase)
    queue.value = [...rest, cue]
    void ensureDrain()
  }

  async function playCue(cue: VoiceCue, epoch: number) {
    abortController = new AbortController()
    playing.value = true
    try {
      const blob = await synthesizeVoiceWav(cue.text, cue.id, abortController.signal)
      if (epoch !== sessionEpoch) return
      await new Promise<void>((resolve, reject) => {
        const url = URL.createObjectURL(blob)
        fallbackAudio = new Audio(url)
        fallbackAudio.onended = () => {
          URL.revokeObjectURL(url)
          fallbackAudio = null
          resolve()
        }
        fallbackAudio.onerror = () => {
          URL.revokeObjectURL(url)
          fallbackAudio = null
          reject(new Error('audio playback failed'))
        }
        void fallbackAudio.play().catch(reject)
      })
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        console.warn('[voice] TTS 合成失败，本条语音已跳过：', err)
      }
    } finally {
      if (epoch === sessionEpoch) {
        abortController = null
        playing.value = false
      }
    }
  }

  async function drain() {
    const epoch = sessionEpoch
    while (enabled.value && epoch === sessionEpoch && queue.value.length > 0) {
      const [current, ...rest] = queue.value
      queue.value = rest
      await playCue(current, epoch)
      if (epoch !== sessionEpoch) break
      if (queue.value.length > 0) await sleep(CUE_GAP_MS)
    }
  }

  function ensureDrain() {
    if (drainPromise) return drainPromise
    drainPromise = drain().finally(() => {
      drainPromise = null
    })
    return drainPromise
  }

  function whenIdle(): Promise<void> {
    if (!enabled.value) return Promise.resolve()
    return new Promise((resolve) => {
      const check = () => {
        if (!enabled.value) {
          resolve()
          return
        }
        if (queue.value.length === 0 && !playing.value && !drainPromise) {
          resolve()
          return
        }
        void (drainPromise ?? Promise.resolve()).finally(() => window.setTimeout(check, 30))
      }
      void ensureDrain().finally(check)
    })
  }

  return {
    enabled,
    playing,
    setEnabled,
    toggleEnabled,
    enqueue,
    interrupt,
    whenIdle,
  }
}
