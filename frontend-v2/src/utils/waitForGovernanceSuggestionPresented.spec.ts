import { describe, expect, it, vi } from 'vitest'
import { STEP_INDICES } from '../constants'
import { waitForGovernanceSuggestionPresented } from './waitForGovernanceSuggestionPresented'

describe('waitForGovernanceSuggestionPresented', () => {
  it('waits until focus step and suggestion card content are both ready', async () => {
    vi.useFakeTimers()
    let focusStepIndex = STEP_INDICES.RULE
    const whenQueueIdle = vi.fn(async () => {})
    const whenSettled = vi.fn(async () => {})

    const promise = waitForGovernanceSuggestionPresented({
      whenQueueIdle,
      whenSettled,
      getFocusStepIndex: () => focusStepIndex,
      getSuggestion: () =>
        focusStepIndex >= STEP_INDICES.SUGGESTION
          ? { narrative: '建议增加东向绿灯 8 秒。' }
          : null,
      getFlowTimingGovernance: () => null,
      pollMs: 20,
    })

    await vi.advanceTimersByTimeAsync(25)
    expect(whenSettled).not.toHaveBeenCalled()

    focusStepIndex = STEP_INDICES.SUGGESTION
    await vi.advanceTimersByTimeAsync(25)

    await promise
    expect(whenQueueIdle).toHaveBeenCalled()
    expect(whenSettled).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('skipQueueIdle avoids waiting on analysis queue when already inside a queue task', async () => {
    const whenQueueIdle = vi.fn(async () => {})
    const whenSettled = vi.fn(async () => {})

    await waitForGovernanceSuggestionPresented({
      whenQueueIdle,
      whenSettled,
      skipQueueIdle: true,
      getFocusStepIndex: () => STEP_INDICES.SUGGESTION,
      getSuggestion: () => ({ narrative: '建议增加东向绿灯 8 秒。' }),
      getFlowTimingGovernance: () => null,
      pollMs: 10,
    })

    expect(whenQueueIdle).not.toHaveBeenCalled()
    expect(whenSettled).toHaveBeenCalled()
  })
})
