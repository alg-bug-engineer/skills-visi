import type { PcmStreamMeta } from './ttsClient'

export class PcmStreamPlayer {
  private audioCtx: AudioContext | null = null
  private nextTime = 0
  private pendingSources = 0
  private allSourcesEnded: Promise<void> | null = null
  private resolveAllSourcesEnded: (() => void) | null = null

  async ensureContext(sampleRate: number): Promise<AudioContext> {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new AudioContext({ sampleRate })
      this.nextTime = this.audioCtx.currentTime
      this.resetSourceTracking()
    }
    if (this.audioCtx.state === 'suspended') {
      await this.audioCtx.resume()
    }
    return this.audioCtx
  }

  private resetSourceTracking(): void {
    this.pendingSources = 0
    this.allSourcesEnded = new Promise((resolve) => {
      this.resolveAllSourcesEnded = resolve
    })
  }

  private markSourceStarted(): void {
    if (this.pendingSources === 0 && this.resolveAllSourcesEnded) {
      this.allSourcesEnded = new Promise((resolve) => {
        this.resolveAllSourcesEnded = resolve
      })
    }
    this.pendingSources += 1
  }

  private markSourceEnded(): void {
    this.pendingSources = Math.max(0, this.pendingSources - 1)
    if (this.pendingSources === 0) {
      this.resolveAllSourcesEnded?.()
      this.resolveAllSourcesEnded = null
    }
  }

  scheduleChunk(pcm: Uint8Array, meta: PcmStreamMeta): void {
    if (!this.audioCtx || pcm.byteLength < 2) return
    const int16 = new Int16Array(pcm.buffer, pcm.byteOffset, pcm.byteLength / 2)
    const buffer = this.audioCtx.createBuffer(1, int16.length, meta.sampleRate)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < int16.length; i += 1) {
      channel[i] = int16[i] / 32768
    }
    const source = this.audioCtx.createBufferSource()
    source.buffer = buffer
    source.connect(this.audioCtx.destination)
    this.markSourceStarted()
    source.onended = () => {
      this.markSourceEnded()
    }
    const startAt = Math.max(this.nextTime, this.audioCtx.currentTime + 0.02)
    source.start(startAt)
    this.nextTime = startAt + buffer.duration
  }

  async drain(tailMs = 220): Promise<void> {
    if (!this.audioCtx) return
    const scheduledWaitMs = Math.max(0, (this.nextTime - this.audioCtx.currentTime) * 1000)
    if (scheduledWaitMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, scheduledWaitMs))
    }
    if (this.pendingSources > 0 && this.allSourcesEnded) {
      await Promise.race([
        this.allSourcesEnded,
        new Promise((resolve) => window.setTimeout(resolve, 5000)),
      ])
    }
    if (tailMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, tailMs))
    }
  }

  close(): void {
    if (this.audioCtx && this.audioCtx.state !== 'closed') {
      void this.audioCtx.close()
    }
    this.audioCtx = null
    this.nextTime = 0
    this.pendingSources = 0
    this.allSourcesEnded = null
    this.resolveAllSourcesEnded = null
  }
}
