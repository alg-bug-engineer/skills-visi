import { afterEach, describe, expect, it, vi } from 'vitest'
import { synthesizeVoiceWav } from '@/services/ttsClient'

describe('ttsClient', () => {
  afterEach(() => vi.restoreAllMocks())

  it('extracts FastAPI detail instead of exposing raw JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        text: async () => '{"detail":"TTS not configured"}',
      })),
    )

    await expect(synthesizeVoiceWav('诊断对象识别。')).rejects.toThrow('TTS 503: TTS not configured')
  })
})
