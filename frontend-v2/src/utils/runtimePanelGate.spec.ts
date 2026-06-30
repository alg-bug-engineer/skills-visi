import { describe, expect, it } from 'vitest'
import { shouldRevealRuntimePanel } from './runtimePanelGate'

describe('shouldRevealRuntimePanel', () => {
  it('requires both data fetch started and cognition done', () => {
    expect(shouldRevealRuntimePanel(false, false)).toBe(false)
    expect(shouldRevealRuntimePanel(true, false)).toBe(false)
    expect(shouldRevealRuntimePanel(false, true)).toBe(false)
    expect(shouldRevealRuntimePanel(true, true)).toBe(true)
  })
})
