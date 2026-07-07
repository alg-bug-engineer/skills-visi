import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'

describe('presentation reset', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('increments mapResetSeq so map overlays are cleared when users reset', () => {
    const store = usePresentationStore()
    const before = store.mapResetSeq

    store.response = { trace_id: 't1', completed: false, pipeline_complete: false, diagnosis_ticket: null, phases: {}, plan: null, phase_results: [] }
    store.currentAct = 4
    store.reset()

    expect(store.response).toBeNull()
    expect(store.currentAct).toBe(-1)
    expect(store.mapResetSeq).toBe(before + 1)
  })
})
