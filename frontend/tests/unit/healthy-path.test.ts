import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { ACT_DEFS, narrationFor, summaryFor } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'

function healthySnap(): RunResponse {
  return {
    trace_id: 't',
    completed: true,
    pipeline_complete: true,
    diagnosis_ticket: null,
    phases: {
      intent: {},
      diagnosis: {
        healthy: true,
        metrics: { queue_ratio: 0.42, saturation: 0.63, los: 'B', green_utilization: 0.71 },
        overflow_verification: { verified: true, risk_level: 'low', message: '溢出风险较低' },
      },
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

const overflowAct = ACT_DEFS.find((a) => a.id === 'act3_overflow')!

describe('健康核验路径', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('isHealthy 反映诊断 healthy 标志', () => {
    const s = usePresentationStore()
    expect(s.isHealthy).toBe(false)
    s.applySnapshot(healthySnap())
    expect(s.isHealthy).toBe(true)
  })

  it('健康时在溢出核验幕后正常收尾，不进入治理幕', () => {
    const s = usePresentationStore()
    s.mode = 'stream'
    s.applySnapshot(healthySnap())
    s.currentAct = overflowAct.index // act3_overflow
    s.tryAdvance()
    expect(s.currentAct).toBe(overflowAct.index)
    expect(s.status).toBe('done')
    expect(s.waiting).toBe(false)
  })

  it('summaryFor/narrationFor 输出健康结论文案', () => {
    const resp = healthySnap()
    expect(summaryFor(overflowAct, resp)).toContain('无需干预')
    const n = narrationFor(overflowAct, resp)
    expect(n.some((l) => l.includes('运行平稳'))).toBe(true)
  })
})
