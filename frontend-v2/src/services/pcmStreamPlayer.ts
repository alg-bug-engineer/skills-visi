import type { PcmStreamMeta } from './ttsClient'

export class PcmStreamPlayer {
  private audioCtx: AudioContext | null = null
  private nextTime = 0

  async ensureContext(sampleRate: number): Promise<AudioContext> {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new AudioContext({ sampleRate })
      this.nextTime = this.audioCtx.currentTime
    }
    if (this.audioCtx.state === 'suspended') {
      await this.audioCtx.resume()
    }
    return this.audioCtx
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
    const startAt = Math.max(this.nextTime, this.audioCtx.currentTime + 0.02)
    source.start(startAt)
    this.nextTime = startAt + buffer.duration
  }

  async drain(extraMs = 80): Promise<void> {
    if (!this.audioCtx) return
    const waitMs = Math.max(0, (this.nextTime - this.audioCtx.currentTime) * 1000 + extraMs)
    if (waitMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, waitMs))
    }
  }

  close(): void {
    if (this.audioCtx && this.audioCtx.state !== 'closed') {
      void this.audioCtx.close()
    }
    this.audioCtx = null
    this.nextTime = 0
  }
}
