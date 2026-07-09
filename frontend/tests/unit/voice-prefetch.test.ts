import { describe, expect, it, vi } from 'vitest'
import { synthesizeVoiceWav } from '@/services/ttsClient'
import { useVoiceNarration } from '@/composables/useVoiceNarration'
import type { VoiceCue } from '@/types/voice'

vi.mock('@/services/ttsClient', () => ({
  synthesizeVoiceWav: vi.fn(() => Promise.resolve(new Blob(['wav'], { type: 'audio/wav' }))),
}))

const cue: VoiceCue = {
  id: 'run:act1:announce',
  stepIndex: 0,
  phase: 'act1_ticket',
  kind: 'guide',
  text: '测试语音',
  priority: 2,
}

describe('voice prefetch', () => {
  it('prefetch 后 play 复用同一次合成请求', async () => {
    localStorage.setItem('voice-narration-enabled', '1')
    const voice = useVoiceNarration()
    vi.mocked(synthesizeVoiceWav).mockClear()

    voice.prefetch(cue)
    await Promise.resolve()
    voice.enqueue(cue)
    await voice.whenIdle()

    expect(synthesizeVoiceWav).toHaveBeenCalledTimes(1)
  })
})
