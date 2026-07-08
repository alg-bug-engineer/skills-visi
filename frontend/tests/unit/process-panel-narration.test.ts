import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import { usePresentationStore } from '@/stores/presentation'
import fixture from '@/mock/run_1_fixture.json'
import type { RunResponse } from '@/api/types'

const fx = fixture as unknown as RunResponse

// webdriver=true → useTyping 走 instant 路径，onDone 同步触发并写入旁白缓存。
let originalWebdriver: PropertyDescriptor | undefined
beforeAll(() => {
  originalWebdriver = Object.getOwnPropertyDescriptor(navigator, 'webdriver')
  Object.defineProperty(navigator, 'webdriver', { value: true, configurable: true })
})
afterAll(() => {
  if (originalWebdriver) Object.defineProperty(navigator, 'webdriver', originalWebdriver)
})

describe('ProcessPanel · 旁白缓存一致性（R2）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('已完成幕展开时显示冻结旁白全文（多行），与打字内容一致', async () => {
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = false // 关闭自动推进，手动控制幕序，避免级联
    store.currentAct = 0

    const wrapper = mount(ProcessPanel)
    await flushPromises()

    // 推进到第 2 幕：第 1 幕成为“已完成”幕，应展示冻结旁白而非仅单行汇总
    store.currentAct = 1
    await flushPromises()

    const frozen = wrapper.findAll('[data-testid="process-narration-frozen"]')
    expect(frozen.length).toBeGreaterThan(0)
    // 第 1 幕旁白首行关键字（仅存在于 narrationFor，不在 summaryFor）
    expect(wrapper.text()).toContain('正在解析')
  })

  it('折叠后再展开仍为多行旁白，不回退成 summaryFor 单行', async () => {
    const store = usePresentationStore()
    store.applySnapshot(fx)
    store.autoPlay = false
    store.currentAct = 0
    const wrapper = mount(ProcessPanel)
    await flushPromises()

    // 逐幕推进，确保 act0/act1/act2 旁白均被缓存
    store.currentAct = 1
    await flushPromises()
    store.currentAct = 2
    await flushPromises()

    // act0 此时默认折叠（index < currentAct - 1）→ 展开它
    const vm = wrapper.vm as unknown as { toggleAct: (i: number) => void }
    vm.toggleAct(0)
    await flushPromises()

    // 展开后应含 act0 的多行旁白关键字
    expect(wrapper.text()).toContain('正在解析')
    const frozen = wrapper.findAll('[data-testid="process-narration-frozen"]')
    expect(frozen.length).toBeGreaterThan(0)
  })
})
