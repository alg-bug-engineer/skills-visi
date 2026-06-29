import { afterEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'voice-narration-enabled'

describe('useVoiceNarration', () => {
  afterEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('defaults voice to enabled when preference is unset', async () => {
    const { useVoiceNarration } = await import('./useVoiceNarration')
    const voice = useVoiceNarration()
    expect(voice.enabled.value).toBe(true)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('1')
  })

  it('respects explicit opt-out', async () => {
    localStorage.setItem(STORAGE_KEY, '0')
    const { useVoiceNarration } = await import('./useVoiceNarration')
    const voice = useVoiceNarration()
    expect(voice.enabled.value).toBe(false)
  })

  it('does not enqueue when disabled', async () => {
    localStorage.setItem(STORAGE_KEY, '0')
    const { useVoiceNarration } = await import('./useVoiceNarration')
    const voice = useVoiceNarration()
    voice.enqueue({
      id: 'test',
      stepIndex: 0,
      phase: 'guide',
      kind: 'guide',
      text: '测试语音',
      priority: 1,
    })
    expect(voice.playing.value).toBe(false)
  })
})
