import { getJSON, postJSON } from './client'
import { streamPost, type StreamHandlers, type StreamController } from './sse'
import type { ApiError, HealthResponse, RunResponse } from './types'
import fixture from '@/mock/run_1_fixture.json'

const MOCK = import.meta.env.VITE_MOCK === '1'

/** 演示句默认输入（对齐 run_1）。 */
export const DEMO_INPUT =
  '奥体西路与经十路交叉口，六点十分到六点半，西向东直行进口道，分析流量溯源和下游拓扑，优先避免下游继续外溢。'

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

export async function health(): Promise<HealthResponse | ApiError> {
  if (MOCK) return { status: 'ok', llm_mock: true, model: 'mock', pg_configured: false }
  return getJSON<HealthResponse>('/health')
}

export interface RunOptions {
  trace_id?: string
  task?: Record<string, unknown>
  skill_ids?: string[]
  stop_after?: string
  signal?: AbortSignal
}

/** 运行智能体。MOCK 模式回放真实 fixture（明确来源，非编造）。 */
export async function runAgent(userInput: string, opts: RunOptions = {}): Promise<RunResponse | ApiError> {
  if (MOCK) {
    await delay(400)
    return fixture as unknown as RunResponse
  }
  return postJSON<RunResponse>(
    '/agent/run',
    {
      user_input: userInput,
      trace_id: opts.trace_id,
      task: opts.task ?? {},
      skill_ids: opts.skill_ids,
      stop_after: opts.stop_after,
    },
    opts.signal,
  )
}

/** 公开 phase 顺序（对齐后端 PHASE_ARTIFACT_KEYS）。 */
const PUBLIC_PHASES: Array<{ phase: string; skill_id: string }> = [
  { phase: 'intent', skill_id: 'intent_understanding' },
  { phase: 'diagnosis', skill_id: 'data_analysis_diagnosis' },
  { phase: 'cause', skill_id: 'cause_analysis' },
  { phase: 'strategy', skill_id: 'strategy_generation' },
  { phase: 'plan', skill_id: 'plan_generation' },
]

const MOCK_PHASE_DELAY = 1400

function mockSnapshotUpTo(i: number): RunResponse {
  const f = fixture as unknown as RunResponse
  const phases: Record<string, unknown> = {}
  for (let k = 0; k <= i; k++) {
    const key = PUBLIC_PHASES[k].phase as keyof RunResponse['phases']
    if (f.phases[key] !== undefined) phases[key] = f.phases[key]
  }
  const last = i === PUBLIC_PHASES.length - 1
  return {
    trace_id: f.trace_id,
    completed: last ? f.completed : null,
    pipeline_complete: last ? f.pipeline_complete : false,
    diagnosis_ticket: f.diagnosis_ticket,
    phases: phases as RunResponse['phases'],
    plan: i >= 4 ? f.plan : null,
    phase_results: (f.phase_results ?? []).slice(0, i + 1),
  }
}

/** 离线模拟流式：按 phase 依次 emit phase_start/phase_done，最后 pipeline_complete。 */
function mockStream(handlers: StreamHandlers): StreamController {
  const timers: number[] = []
  let stopped = false
  handlers.onStatus?.('open', 0)
  PUBLIC_PHASES.forEach((p, i) => {
    const t0 = window.setTimeout(() => {
      if (stopped) return
      handlers.onEvent?.({ event: 'phase_start', data: { ...p, index: i, total: PUBLIC_PHASES.length } })
    }, i * MOCK_PHASE_DELAY + 200)
    const t1 = window.setTimeout(() => {
      if (stopped) return
      handlers.onEvent?.({
        event: 'phase_done',
        data: { ...p, index: i, total: PUBLIC_PHASES.length, success: true, duration_ms: 0, snapshot: mockSnapshotUpTo(i) },
      })
      if (i === PUBLIC_PHASES.length - 1) {
        handlers.onEvent?.({ event: 'pipeline_complete', data: { snapshot: mockSnapshotUpTo(i) } })
        handlers.onDone?.()
      }
    }, i * MOCK_PHASE_DELAY + MOCK_PHASE_DELAY)
    timers.push(t0, t1)
  })
  return {
    close() {
      stopped = true
      timers.forEach((t) => clearTimeout(t))
    },
  }
}

/** 流式运行智能体：真实走 /agent/run/stream；MOCK 走离线模拟。 */
export function runAgentStream(userInput: string, handlers: StreamHandlers, opts: RunOptions = {}): StreamController {
  if (MOCK) return mockStream(handlers)
  return streamPost(
    '/api/v1/agent/run/stream',
    {
      user_input: userInput,
      trace_id: opts.trace_id,
      task: opts.task ?? {},
      skill_ids: opts.skill_ids,
      stop_after: opts.stop_after,
    },
    handlers,
  )
}

export interface RegenerateOptions {
  trace_id: string
  user_input: string
  task: Record<string, unknown>
  restart_from?: string
}

export async function regeneratePlan(opts: RegenerateOptions): Promise<RunResponse | ApiError> {
  if (MOCK) {
    await delay(500)
    return fixture as unknown as RunResponse
  }
  return postJSON<RunResponse>('/agent/plan/regenerate', {
    trace_id: opts.trace_id,
    user_input: opts.user_input,
    task: opts.task,
    restart_from: opts.restart_from ?? 'plan_generation',
  })
}

export interface DecisionOptions {
  trace_id: string
  plan_id: string
  decision: 'accept' | 'reject'
  rejection_reason?: string
  plan_snapshot?: unknown
  diagnosis_ticket?: unknown
  artifacts_summary?: unknown
}

export async function submitDecision(opts: DecisionOptions): Promise<Record<string, unknown> | ApiError> {
  if (MOCK) {
    await delay(200)
    return { ok: true, recorded: true, source: 'mock' }
  }
  return postJSON('/agent/plan/decision', opts)
}

export interface CaseItem {
  case_id?: string
  category?: string
  title?: string
  lesson?: string
  [k: string]: unknown
}

export async function listCases(params: {
  problem_type?: string
  inter_id?: string
  category?: string
  limit?: number
}): Promise<{ cases: CaseItem[]; total?: number } | ApiError> {
  if (MOCK) {
    await delay(200)
    return {
      cases: [
        { case_id: 'demo-1', category: 'recommended', title: '干线联控成功案例', lesson: '上游控流+小步释放+下游保护' },
        { case_id: 'demo-2', category: 'risk', title: '单点激进加绿失败', lesson: '下游继续外溢' },
      ],
      total: 2,
    }
  }
  return getJSON('/agent/cases', params)
}

export async function loadIntersection(body: Record<string, unknown>): Promise<Record<string, unknown> | ApiError> {
  if (MOCK) return { ok: false, reason: 'mock_mode' }
  return postJSON('/intersection/load', body)
}
