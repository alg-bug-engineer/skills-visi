import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from '@/App.vue'
import { ACT_DEFS } from '@/composables/useTimeline'
import { usePresentationStore } from '@/stores/presentation'
import * as voiceStepSync from '@/services/voiceStepSync'

vi.mock('@/services/ttsClient', () => ({
  synthesizeVoiceWav: vi.fn(() => new Promise(() => {})),
}))

describe('voice · act 进入时并行触发', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    voiceStepSync.resetActVoiceKeys()
    localStorage.clear()
  })

  it('currentAct 切换时立即入队语音（不等待打字完成）', async () => {
    const cueSpy = vi.spyOn(voiceStepSync, 'voiceCueForAct')
    mount(App, {
      global: {
        stubs: {
          AMapProvider: true,
          UnderstandingPanel: true,
          RunningDataPanel: true,
          ProcessPanel: true,
          BottomDock: true,
          DownstreamTopologyInset: true,
          SkillSolidifyOverlay: true,
          SkillBuildDrawer: true,
        },
      },
    })

    const store = usePresentationStore()
    cueSpy.mockClear()
    store.currentAct = 2
    await Promise.resolve()

    expect(cueSpy).toHaveBeenCalledWith(ACT_DEFS[2], expect.any(String), store.response)
  })
})
