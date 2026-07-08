import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { useVoiceNarration } from '@/composables/useVoiceNarration'
import { synthesizeVoiceWav } from '@/services/ttsClient'

vi.mock('@/services/ttsClient', () => ({
  synthesizeVoiceWav: vi.fn(),
}))

describe('voice narration error state', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(synthesizeVoiceWav).mockReset()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it('exposes a visible error when TTS synthesis fails', async () => {
    vi.mocked(synthesizeVoiceWav).mockRejectedValue(new Error('TTS 503: TTS not configured'))
    const voice = useVoiceNarration()

    voice.enqueue({
      id: 'run-1:act1:announce',
      stepIndex: 0,
      phase: 'act1_ticket',
      kind: 'guide',
      text: '诊断对象识别。',
      priority: 2,
    })

    await voice.whenIdle()
    await nextTick()

    expect(voice.error.value).toContain('语音播报不可用')
    expect(voice.error.value).toContain('TTS not configured')
  })
})
