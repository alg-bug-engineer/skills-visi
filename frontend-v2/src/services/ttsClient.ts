const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export interface PcmStreamMeta {
  sampleRate: number
  channels: number
  sampleWidth: number
}

function parsePcmMeta(res: Response): PcmStreamMeta {
  return {
    sampleRate: Number(res.headers.get('X-Audio-Sample-Rate') ?? 24000),
    channels: Number(res.headers.get('X-Audio-Channels') ?? 1),
    sampleWidth: Number(res.headers.get('X-Audio-Sample-Width') ?? 2),
  }
}

/** Stream PCM and invoke callback for each chunk (low latency). */
export async function streamVoicePcm(
  text: string,
  onChunk: (pcm: Uint8Array, meta: PcmStreamMeta) => void,
  cueId?: string,
  signal?: AbortSignal,
): Promise<PcmStreamMeta> {
  const res = await fetch(`${API_BASE}/api/v1/tts/synthesize/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, cue_id: cueId }),
    signal,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`TTS stream ${res.status}: ${detail.slice(0, 200)}`)
  }
  if (!res.body) {
    throw new Error('TTS stream missing body')
  }

  const meta = parsePcmMeta(res)
  const reader = res.body.getReader()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (value?.byteLength) onChunk(value, meta)
  }
  return meta
}

/** Fallback: full WAV synthesis. */
export async function synthesizeVoiceWav(text: string, cueId?: string, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/tts/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, cue_id: cueId }),
    signal,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`TTS ${res.status}: ${detail.slice(0, 200)}`)
  }
  return res.blob()
}
