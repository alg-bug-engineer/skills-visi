import { getJSON, postJSON } from './client'
import type { ApiError, HealthResponse, RunResponse } from './types'
import fixture from '@/mock/run_1_fixture.json'

const MOCK = import.meta.env.VITE_MOCK === '1'

/** 演示句默认输入（对齐 run_1）。 */
export const DEMO_INPUT =
  '转山西路与经十路交叉口，六点十分到六点半，东向西排队溢出到上游，优先避免下游继续外溢。'

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
