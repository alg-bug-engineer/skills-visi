import { ref, shallowRef } from 'vue'
import type { VoiceCue } from '../types/voice'
import { PcmStreamPlayer } from '../services/pcmStreamPlayer'
import { streamVoicePcm, synthesizeVoiceWav } from '../services/ttsClient'

const STORAGE_KEY = 'voice-narration-enabled'

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

export function useVoiceNarration() {
  const enabled = ref(localStorage.getItem(STORAGE_KEY) === '1')
  const playing = ref(false)
  const queue = shallowRef<VoiceCue[]>([])
  let pcmPlayer: PcmStreamPlayer | null = null
  let fallbackAudio: HTMLAudioElement | null = null
  let sessionEpoch = 0
  let abortController: AbortController | null = null
  let drainPromise: Promise<void> | null = null

  function setEnabled(value: boolean) {
    enabled.value = value
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
    if (!value) interrupt()
  }

  function toggleEnabled() {
    setEnabled(!enabled.value)
  }

  function stopPlayback() {
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

  function interrupt() {
    sessionEpoch += 1
    queue.value = []
    stopPlayback()
    drainPromise = null
  }

  function enqueue(cue: VoiceCue | null | undefined) {
    if (!cue || !enabled.value) return

    const items = [...queue.value]
    const sameStep = items.findIndex((item) => item.stepIndex === cue.stepIndex && item.phase === cue.phase)
    if (sameStep >= 0) items.splice(sameStep, 1)
    items.push(cue)

    if (cue.priority >= 2 && playing.value) {
      stopPlayback()
      queue.value = [cue, ...items.filter((item) => item.id !== cue.id)]
    } else {
      queue.value = items
    }

    void ensureDrain()
  }

  async function playCueStream(cue: VoiceCue, epoch: number): Promise<boolean> {
    playing.value = true
    abortController = new AbortController()
    pcmPlayer = new PcmStreamPlayer()
    let receivedBytes = 0

    try {
      await streamVoicePcm(
        cue.text,
        (chunk, meta) => {
          if (epoch !== sessionEpoch) return
          receivedBytes += chunk.byteLength
          void pcmPlayer?.ensureContext(meta.sampleRate).then(() => {
            pcmPlayer?.scheduleChunk(chunk, meta)
          })
        },
        cue.id,
        abortController.signal,
      )
      if (epoch !== sessionEpoch) return false
      await pcmPlayer.drain()
      return receivedBytes > 0
    } catch (err) {
      if (epoch !== sessionEpoch || isAbortError(err)) return false
      if (receivedBytes > 0) {
        await pcmPlayer.drain()
        return true
      }
      return false
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
          fallbackAudio = null
          resolve()
        }
        fallbackAudio.onerror = () => {
          URL.revokeObjectURL(url)
          fallbackAudio = null
          reject(new Error('audio playback failed'))
        }
        playing.value = true
        void fallbackAudio.play().catch(reject)
      })
    } catch {
      /* silent degrade */
    } finally {
      if (epoch === sessionEpoch) {
        playing.value = false
      }
    }
  }

  async function playCue(cue: VoiceCue, epoch: number) {
    const streamed = await playCueStream(cue, epoch)
    if (epoch !== sessionEpoch) return
    if (!streamed) {
      await playCueWavFallback(cue, epoch)
    }
  }

  async function drain() {
    const epoch = sessionEpoch
    while (enabled.value && epoch === sessionEpoch && queue.value.length > 0) {
      const [current, ...rest] = queue.value
      queue.value = rest
      await playCue(current, epoch)
    }
  }

  function ensureDrain() {
    if (drainPromise) return drainPromise
    drainPromise = drain().finally(() => {
      drainPromise = null
    })
    return drainPromise
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
