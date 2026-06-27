import { describe, expect, it, vi } from 'vitest'
import { STEP_INDICES } from '../constants'
import { useUnderstandingProcess } from '../composables/useUnderstandingProcess'

describe('useUnderstandingProcess onStepStart', () => {
  it('fires when a step is first created, not when appending to the same step', () => {
    const onStepStart = vi.fn()
    const { enqueue } = useUnderstandingProcess({ onStepStart })

    enqueue(STEP_INDICES.COGNITION, '路段 A')
    expect(onStepStart).toHaveBeenCalledTimes(1)
    expect(onStepStart).toHaveBeenCalledWith(STEP_INDICES.COGNITION)

    enqueue(STEP_INDICES.COGNITION, '路段 B', true)
    expect(onStepStart).toHaveBeenCalledTimes(1)
  })
})
