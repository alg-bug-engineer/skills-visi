const API_BASE = '/api/v1'

export async function synthesizeVoiceWav(
  text: string,
  cueId?: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/tts/synthesize`, {
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
