import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { useStepPauseKeyboard } from '@/composables/useStepPause'
import { usePresentationStore } from '@/stores/presentation'

const Host = defineComponent({
  setup() {
    useStepPauseKeyboard()
    return () => null
  },
})

describe('useStepPauseKeyboard', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('运行态空格切换 stepPaused', async () => {
    const store = usePresentationStore()
    store.status = 'running'
    store.currentAct = 0
    mount(Host)

    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }))
    expect(store.stepPaused).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }))
    expect(store.stepPaused).toBe(false)
  })

  it('输入框聚焦时不触发暂停', async () => {
    const store = usePresentationStore()
    store.status = 'running'
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    mount(Host)

    input.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }))
    expect(store.stepPaused).toBe(false)
  })

  it('技能阶段报错后演示继续时仍可空格暂停', async () => {
    const store = usePresentationStore()
    store.status = 'error'
    store.currentAct = 3
    mount(Host)

    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }))
    expect(store.stepPaused).toBe(true)
  })
})
