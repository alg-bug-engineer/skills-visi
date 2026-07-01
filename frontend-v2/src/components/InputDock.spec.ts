import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InputDock from './InputDock.vue'
import { DEFAULT_PROMPT } from '../constants'

function mountDock(docked: boolean) {
  return mount(InputDock, {
    props: {
      docked,
      locked: false,
      loading: false,
    },
  })
}

describe('InputDock submit', () => {
  it('uses default prompt on homepage when input is empty', async () => {
    const wrapper = mountDock(false)
    await wrapper.get('[data-testid="send-button"]').trigger('click')
    expect(wrapper.emitted('send')?.[0]).toEqual([DEFAULT_PROMPT])
    expect(wrapper.emitted('notify')).toBeUndefined()
  })

  it('shows notify toast when docked and input is empty', async () => {
    const wrapper = mountDock(true)
    await wrapper.get('[data-testid="send-button"]').trigger('click')
    expect(wrapper.emitted('send')).toBeUndefined()
    expect(wrapper.emitted('notify')?.[0]).toEqual(['请输入内容后再发送'])
  })

  it('clears placeholder on docked view', () => {
    const wrapper = mountDock(true)
    expect(wrapper.get('textarea').attributes('placeholder')).toBe('')
  })

  it('shows default prompt placeholder on homepage', () => {
    const wrapper = mountDock(false)
    expect(wrapper.get('textarea').attributes('placeholder')).toBe(DEFAULT_PROMPT)
  })
})
