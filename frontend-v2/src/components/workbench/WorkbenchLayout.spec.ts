import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkbenchLayout from './WorkbenchLayout.vue'
import { SUGGESTION_CONFIRM_BANNER } from '../../constants'
import { createInitialPresentation } from '../../types/presentation'

const baseProps = {
  presentation: {
    ...createInitialPresentation(),
    phase: 'evidence' as const,
    cognition: { intersection: { name: '测试路口', inter_id: 'test' } },
  },
  mapActions: [],
  processSteps: [],
  panelMode: 'analysis' as const,
  conversation: [],
  missingFields: [],
  processActive: false,
  docked: true,
  inputLocked: false,
  loading: false,
  followUpBubble: null,
  mapToast: null,
  showConfirm: false,
  confirmMessage: '',
  errorBanner: null,
}

describe('WorkbenchLayout confirm banners', () => {
  it('shows space-pause toast only when presentation is paused without suggestion confirm', () => {
    const wrapper = mount(WorkbenchLayout, {
      props: {
        ...baseProps,
        presentationPaused: true,
        suggestionConfirmBanner: null,
      },
    })
    expect(wrapper.find('[data-testid="presentation-pause"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="suggestion-confirm-banner"]').exists()).toBe(false)
  })

  it('shows suggestion confirm banner instead of space-pause toast', () => {
    const wrapper = mount(WorkbenchLayout, {
      props: {
        ...baseProps,
        presentationPaused: true,
        suggestionConfirmBanner: SUGGESTION_CONFIRM_BANNER,
      },
    })
    expect(wrapper.find('[data-testid="presentation-pause"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="suggestion-confirm-banner"]').text()).toBe(
      SUGGESTION_CONFIRM_BANNER,
    )
  })
})
