import { ref, shallowRef } from 'vue'
import type { VoiceCue } from '../types/voice'
import { PcmStreamPlayer } from '../services/pcmStreamPlayer'
import { streamVoicePcm, synthesizeVoiceWav } from '../services/ttsClient'

const STORAGE_KEY = 'voice-narration-enabled'

export function useVoiceNarration() {
  const enabled = ref(localStorage.getItem(STORAGE_KEY) === '1')
  const playing = ref(false)
  const queue = shallowRef<VoiceCue[]>([])
  let pcmPlayer: PcmStreamPlayer | null = null
  let fallbackAudio: HTMLAudioElement | null = null
  let sessionEpoch = 0
  let abortController: AbortController | null = null

  function setEnabled(value: boolean) {
    enabled.value = value
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
    if (!value) interrupt()
  }

  function toggleEnabled() {
    setEnabled(!enabled.value)
  }

  function interrupt() {
    sessionEpoch += 1
    queue.value = []
    abortController?.abort()
    abortController = null
    pcmPlayer?.close()
    pcmPlayer = null
    if (fallbackAudio) {
      fallbackAudio.pause()
      fallbackAudio.src = ''
      fallbackAudio = null
    }
    playing.value = false
  }

  function enqueue(cue: VoiceCue | null | undefined) {
    if (!cue || !enabled.value) return

    const items = [...queue.value]
    const sameStep = items.findIndex((item) => item.stepIndex === cue.stepIndex && item.phase === cue.phase)
    if (sameStep >= 0) items.splice(sameStep, 1)
    items.push(cue)

    if (cue.priority >= 2 && playing.value) {
      abortController?.abort()
      pcmPlayer?.close()
      pcmPlayer = null
      playing.value = false
      queue.value = [cue, ...items.filter((item) => item.id !== cue.id)]
    } else {
      queue.value = items
    }

    void drain()
  }

  async function playCueStream(cue: VoiceCue, epoch: number) {
    playing.value = true
    abortController = new AbortController()
    pcmPlayer = new PcmStreamPlayer()
    try {
      await streamVoicePcm(
        cue.text,
        (chunk, meta) => {
          if (epoch !== sessionEpoch) return
          void pcmPlayer?.ensureContext(meta.sampleRate).then(() => {
            pcmPlayer?.scheduleChunk(chunk, meta)
          })
        },
        cue.id,
        abortController.signal,
      )
      if (epoch !== sessionEpoch) return
      await pcmPlayer.drain()
    } catch {
      if (epoch !== sessionEpoch) return
      await playCueWavFallback(cue, epoch)
    } finally {
      if (epoch === sessionEpoch) {
        pcmPlayer?.close()
        pcmPlayer = null
        abortController = null
        playing.value = false
      }
    }
  }

  async function playCueWavFallback(cue: VoiceCue, epoch: number) {
    try {
      const blob = await synthesizeVoiceWav(cue.text, cue.id)
      if (epoch !== sessionEpoch) return
      await new Promise<void>((resolve, reject) => {
        const url = URL.createObjectURL(blob)
        fallbackAudio = new Audio(url)
        fallbackAudio.onended = () => {
          URL.revokeObjectURL(url)
          resolve()
        }
        fallbackAudio.onerror = () => {
          URL.revokeObjectURL(url)
          reject(new Error('audio playback failed'))
        }
        void fallbackAudio.play().catch(reject)
      })
    } catch {
      /* silent degrade */
    }
  }

  async function drain() {
    const epoch = sessionEpoch
    while (enabled.value && epoch === sessionEpoch && queue.value.length > 0) {
      const [current, ...rest] = queue.value
      queue.value = rest
      await playCueStream(current, epoch)
    }
  }

  function resetSession() {
    interrupt()
  }

  return {
    enabled,
    playing,
    setEnabled,
    toggleEnabled,
    enqueue,
    interrupt,
    resetSession,
  }
}
