import { describe, expect, it } from 'vitest'
import { STEP_INDICES } from '../constants'
import { usePresentationSequence } from './usePresentationSequence'

describe('usePresentationSequence', () => {
  it('reveals insight stack at problem evidence step', () => {
    const seq = usePresentationSequence()
    seq.syncFromStepIndex(STEP_INDICES.COGNITION)
    expect(seq.layers.value.insightStack).toBe(false)

    seq.syncFromStepIndex(STEP_INDICES.PROBLEM_EVIDENCE)
    expect(seq.layers.value.insightStack).toBe(true)
    expect(seq.layers.value.evidenceNote).toBe(true)
  })

  it('defers timing ring auto until rule step', () => {
    const seq = usePresentationSequence()
    seq.syncFromStepIndex(STEP_INDICES.DATA_FETCH)
    seq.syncFromPhase('timing')
    expect(seq.layers.value.timingRingAuto).toBe(false)

    seq.syncFromStepIndex(STEP_INDICES.RULE)
    expect(seq.layers.value.timingRingAuto).toBe(true)
  })

  it('resets gates on reset()', () => {
    const seq = usePresentationSequence()
    seq.syncFromStepIndex(STEP_INDICES.RULE)
    seq.reset()
    expect(seq.focusStepIndex.value).toBe(-1)
  })
})
