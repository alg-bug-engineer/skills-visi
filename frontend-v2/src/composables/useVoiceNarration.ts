import { ref, shallowRef } from 'vue'
import type { VoiceCue } from '../types/voice'
import { synthesizeVoice } from '../services/ttsClient'

const STORAGE_KEY = 'voice-narration-enabled'

export function useVoiceNarration() {
  const enabled = ref(localStorage.getItem(STORAGE_KEY) === '1')
  const playing = ref(false)
  const queue = shallowRef<VoiceCue[]>([])
  let audio: HTMLAudioElement | null = null
  let prefetchBlob: Blob | null = null
  let prefetchCueId: string | null = null
  let sessionEpoch = 0

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
    prefetchBlob = null
    prefetchCueId = null
    if (audio) {
      audio.pause()
      audio.src = ''
      audio = null
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
      if (audio) {
        audio.pause()
        audio.src = ''
        audio = null
      }
      playing.value = false
      prefetchBlob = null
      prefetchCueId = null
      queue.value = [cue, ...items.filter((item) => item.id !== cue.id)]
    } else {
      queue.value = items
    }

    void drain()
  }

  async function prefetchNext(next: VoiceCue, epoch: number) {
    if (prefetchCueId === next.id && prefetchBlob) return
    try {
      const blob = await synthesizeVoice(next.text, next.id)
      if (epoch !== sessionEpoch) return
      prefetchBlob = blob
      prefetchCueId = next.id
    } catch {
      prefetchBlob = null
      prefetchCueId = null
    }
  }

  async function playCue(cue: VoiceCue, epoch: number) {
    playing.value = true
    try {
      let blob: Blob
      if (prefetchCueId === cue.id && prefetchBlob) {
        blob = prefetchBlob
        prefetchBlob = null
        prefetchCueId = null
      } else {
        blob = await synthesizeVoice(cue.text, cue.id)
      }
      if (epoch !== sessionEpoch) return

      await new Promise<void>((resolve, reject) => {
        const url = URL.createObjectURL(blob)
        audio = new Audio(url)
        audio.onended = () => {
          URL.revokeObjectURL(url)
          resolve()
        }
        audio.onerror = () => {
          URL.revokeObjectURL(url)
          reject(new Error('audio playback failed'))
        }
        void audio.play().catch(reject)
      })
    } catch {
      /* silent degrade */
    } finally {
      if (epoch === sessionEpoch) playing.value = false
    }
  }

  async function drain() {
    const epoch = sessionEpoch
    while (enabled.value && epoch === sessionEpoch && queue.value.length > 0) {
      const [current, ...rest] = queue.value
      queue.value = rest
      if (rest[0]) void prefetchNext(rest[0], epoch)
      await playCue(current, epoch)
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
