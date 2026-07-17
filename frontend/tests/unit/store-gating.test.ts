import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { RunResponse } from '@/api/types'

function snap(phases: string[], withPlan = false): RunResponse {
  const p: Record<string, unknown> = {}
  for (const k of phases) p[k] = {}
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: p as RunResponse['phases'],
    plan: withPlan ? ({ candidates: [] } as unknown as RunResponse['plan']) : null,
    phase_results: [],
  }
}

describe('presentation store · 流式门控', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('首个意图快照到达才进入第一幕', () => {
    const s = usePresentationStore()
    s.mode = 'stream'
    s.currentAct = -1
    // 尚无数据
    s.resumeIfReady()
    expect(s.currentAct).toBe(-1)
    // 意图到达
    s.applySnapshot(snap(['intent']))
    s.resumeIfReady()
    expect(s.currentAct).toBe(0)
  })

  it('同 phase 内可推进，跨未就绪 phase 进入等待', () => {
    const s = usePresentationStore()
    s.mode = 'stream'
    s.applySnapshot(snap(['intent']))
    s.currentAct = 0
    // act0(intent) → act1(intent) 就绪，直接推进
    s.tryAdvance()
    expect(s.currentAct).toBe(1)
    const key = s.actBarrierKey
    s.completeActBarrier('typing', 1, key)
    s.completeActBarrier('voice', 1, key)
    s.completeActBarrier('map', 1, key)
    // act1(intent) → act2(diagnosis) 未就绪，进入等待
    s.tryAdvance()
    expect(s.currentAct).toBe(1)
    expect(s.waiting).toBe(true)
    expect(s.computingPhase).toBe('diagnosis')
    // 诊断到达后自动续推
    s.applySnapshot(snap(['intent', 'diagnosis']))
    s.resumeIfReady()
    expect(s.waiting).toBe(false)
    expect(s.currentAct).toBe(2)
  })

  it('三栅栏齐备前不推进，旧 act key 不能穿透', () => {
    const s = usePresentationStore()
    s.mode = 'batch'
    s.applySnapshot(snap(['intent', 'diagnosis', 'cause', 'strategy'], true))
    s.beginAct(0)
    const oldKey = s.actBarrierKey
    s.completeActBarrier('typing', 0, oldKey)
    s.completeActBarrier('voice', 0, oldKey)
    s.tryAdvance()
    expect(s.currentAct).toBe(0)
    s.completeActBarrier('map', 0, oldKey)
    s.tryAdvance()
    expect(s.currentAct).toBe(1)
    s.completeActBarrier('map', 0, oldKey)
    expect(s.actBarriers.map).toBe(false)
  })

  it('batch 模式忽略门控，直接推进', () => {
    const s = usePresentationStore()
    s.mode = 'batch'
    s.applySnapshot(snap(['intent'])) // 仅意图，但 batch 不门控
    s.currentAct = 1
    s.tryAdvance()
    expect(s.currentAct).toBe(2)
    expect(s.waiting).toBe(false)
  })

  it('末幕后标记完成', () => {
    const s = usePresentationStore()
    s.mode = 'batch'
    s.currentAct = s.lastActIndex
    s.tryAdvance()
    expect(s.status).toBe('done')
  })

  it('goToAct 在流式下受 phase 门控', () => {
    const s = usePresentationStore()
    s.mode = 'stream'
    s.applySnapshot(snap(['intent']))
    s.currentAct = 0
    s.goToAct(7) // plan 未就绪 → 拒绝
    expect(s.currentAct).toBe(0)
    s.applySnapshot(snap(['intent', 'diagnosis', 'cause', 'strategy'], true))
    s.goToAct(7) // plan 就绪 → 允许
    expect(s.currentAct).toBe(7)
  })
})
