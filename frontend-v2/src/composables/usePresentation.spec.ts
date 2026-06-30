import { describe, expect, it } from 'vitest'
import { usePresentation } from './usePresentation'

describe('usePresentation runtime panel reveal', () => {
  it('reveals runtime panel only when revealRuntimePanel is called', () => {
    const { state, revealRuntimePanel, mergeDataInsight } = usePresentation()
    mergeDataInsight({
      title: '运行数据',
      metrics: [{ label: '延误指数', value: '1.88' }],
    })
    expect(state.revealedInsightSteps.runtimePanel).toBe(false)
    revealRuntimePanel()
    expect(state.revealedInsightSteps.runtimePanel).toBe(true)
    expect(state.revealedInsightSteps.data).toBe(false)
  })

  it('reveals data insight card on revealDataCard after DATA_FETCH step completes', () => {
    const { state, mergeDataInsight, revealDataCard } = usePresentation()
    mergeDataInsight({
      title: '运行数据',
      metrics: [{ label: '延误指数', value: '1.88' }],
    })
    revealDataCard()
    expect(state.revealedInsightSteps.data).toBe(true)
    expect(state.insightCards.some((c) => c.kind === 'data')).toBe(true)
  })

  it('clears runtimePanel on prepareNewAnalysisRun', () => {
    const { state, revealRuntimePanel, prepareNewAnalysisRun } = usePresentation()
    revealRuntimePanel()
    prepareNewAnalysisRun()
    expect(state.revealedInsightSteps.runtimePanel).toBe(false)
  })
})
