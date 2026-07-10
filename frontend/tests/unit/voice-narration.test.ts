import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import App from '@/App.vue'
import { ACT_DEFS } from '@/composables/useTimeline'
import { usePresentationStore } from '@/stores/presentation'
import { resetActVoiceKeys, voiceCueForAct } from '@/services/voiceStepSync'
import * as voiceStepSync from '@/services/voiceStepSync'
import { useVoiceNarration } from '@/composables/useVoiceNarration'
import { synthesizeVoiceWav } from '@/services/ttsClient'
import fixture from '@/mock/run_1_fixture.json'
import type { RunResponse } from '@/api/types'
import type { VoiceCue } from '@/types/voice'

const fx = fixture as unknown as RunResponse

const APP_STUBS = {
  AMapProvider: true,
  UnderstandingPanel: true,
  RunningDataPanel: true,
  ProcessPanel: true,
  BottomDock: true,
  SkillSolidifyOverlay: true,
  SkillBuildDrawer: true,
}

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

describe('voice narration step sync', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetActVoiceKeys()
    localStorage.clear()
  })

  it('maps each process act to template announce with purpose and diagnosis conclusion', () => {
    const announce = voiceCueForAct(ACT_DEFS[0], 'run-1', fx)
    expect(announce?.text).toContain('诊断对象识别')
    expect(announce?.text).not.toContain('核心结论')
    expect(announce?.phase).toBe('act1_ticket')
    expect(voiceCueForAct(ACT_DEFS[0], 'run-1', fx)).toBeNull()

    const locate = voiceCueForAct(ACT_DEFS[1], 'run-1', fx)
    expect(locate?.text).toContain('诊断对象定位')
    expect(locate?.text).not.toContain('已锁定')

    const overflow = voiceCueForAct(ACT_DEFS[2], 'run-1', fx)
    expect(overflow?.text).not.toContain('核心结论')
    expect(overflow?.text).toContain(fx.phases?.diagnosis?.overflow_verification?.message ?? '')
  })

  it('currentAct 切换时立即入队语音（不等待打字完成）', async () => {
    const cueSpy = vi.spyOn(voiceStepSync, 'voiceCueForAct')
    mount(App, { global: { stubs: APP_STUBS } })

    const store = usePresentationStore()
    cueSpy.mockClear()
    store.currentAct = 2
    await Promise.resolve()

    expect(cueSpy).toHaveBeenCalledWith(ACT_DEFS[2], expect.any(String), store.response)
  })

  it('shows a default-on speaker toggle beside map focus and clears voice when closed', async () => {
    const wrapper = mount(App, { global: { stubs: APP_STUBS } })

    const store = usePresentationStore()
    const interrupt = vi.spyOn(store, 'interruptVoice')
    const btn = wrapper.get('[data-testid="voice-toggle"]')
    expect(btn.attributes('aria-pressed')).toBe('true')
    expect(btn.text()).toContain('语音播报')

    await btn.trigger('click')

    expect(btn.attributes('aria-pressed')).toBe('false')
    expect(localStorage.getItem('voice-narration-enabled')).toBe('0')
    expect(interrupt).toHaveBeenCalled()
  })
})

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

describe('ttsClient', () => {
  afterEach(() => vi.restoreAllMocks())

  it('extracts FastAPI detail instead of exposing raw JSON', async () => {
    const { synthesizeVoiceWav: realSynth } =
      await vi.importActual<typeof import('@/services/ttsClient')>('@/services/ttsClient')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        text: async () => '{"detail":"TTS not configured"}',
      })),
    )

    await expect(realSynth('诊断对象识别。')).rejects.toThrow('TTS 503: TTS not configured')
  })
})
