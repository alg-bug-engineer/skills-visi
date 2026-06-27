import type { ProblemEvidence, QuantitativeConstraints } from './evidence'

export interface ReplyPayload {
  type: 'follow_up' | 'diagnosis' | 'skill_created' | 'skill_updated' | 'text' | 'error'
  content: string
}

export interface MessageResponse {
  session_id: string
  state: string
  reply: ReplyPayload
  nlu?: Record<string, unknown> | null
  diagnosis?: Record<string, unknown> | null
  suggestion?: Record<string, unknown> | null
  meta?: MessageMeta
}

export interface MessageMeta {
  matched_skill?: string | null
  skill_reused?: boolean
  skill_match_reason?: string
  resolution_source?: string | null
  inter_id?: string | null
  data_window?: DataWindowMeta
  query_trace?: unknown[]
  cognition?: CognitionMeta
  problem_evidence?: ProblemEvidence
  quantitative_constraints?: QuantitativeConstraints
  suggestion_action?: string
  skill_action?: string
  [key: string]: unknown
}

export interface ExecutionStepEvent {
  event: 'step' | 'result' | 'error' | 'done'
  step?: string
  status?: 'running' | 'completed' | 'failed'
  label?: string
  data?: Record<string, unknown>
  message?: string
  detail?: string
  timestamp?: string
}

export type SseStreamEvent =
  | ExecutionStepEvent
  | import('./skillBuild').SkillBuildEvent
  | import('./skillAbsorption').SkillAbsorptionEvent

export interface CognitionMeta {
  intersection?: Record<string, unknown>
  arms?: unknown[]
  direction_groups?: unknown[]
  available_directions?: string[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  replyType?: string
  meta?: Record<string, unknown>
}

export interface StepRecord {
  step: string
  label: string
  status: string
  data?: Record<string, unknown>
  timestamp?: string
}

export interface DataWindowMeta {
  type: string
  reference_date: string
  date_from: string
  date_to: string
  time_slot?: string
  time_label?: string
  dow_filter?: number[]
  primary_dow?: number
  dws_dow_filter?: number[]
  fallback_reason?: string
  step_index_range?: number[]
  window_days?: number
  source_tier?: string
  sample_count?: number
}
