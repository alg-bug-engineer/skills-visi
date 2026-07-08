import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from '@/App.vue'
import { ACT_DEFS } from '@/composables/useTimeline'
import { usePresentationStore } from '@/stores/presentation'
import { resetActVoiceKeys, voiceCueForAct } from '@/services/voiceStepSync'

describe('voice narration step sync', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetActVoiceKeys()
    localStorage.clear()
  })

  it('maps each process act to a short fixed announce cue and dedupes per run', () => {
    const cue = voiceCueForAct(ACT_DEFS[0], 'run-1')
    expect(cue?.text).toBe('诊断对象识别。')
    expect(cue?.phase).toBe('act1_ticket')
    expect(voiceCueForAct(ACT_DEFS[0], 'run-1')).toBeNull()

    const locate = voiceCueForAct(ACT_DEFS[1], 'run-1')
    expect(locate?.text).toBe('诊断对象定位。')
  })

  it('shows a default-on speaker toggle beside map focus and clears voice when closed', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          AMapProvider: true,
          UnderstandingPanel: true,
          RunningDataPanel: true,
          ProcessPanel: true,
          BottomDock: true,
          ChannelizationInset: true,
          DownstreamTopologyInset: true,
          SkillSolidifyOverlay: true,
          SkillBuildDrawer: true,
        },
      },
    })

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
