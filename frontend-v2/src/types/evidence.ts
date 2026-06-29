/** Problem validation evidence & quantitative constraints (backend meta, 0625+). */

export interface EvidenceChronic {
  is_chronic?: boolean
  congested_days?: number | null
  window_days?: number
  rate?: number | null
  congested_dates?: string[]
  verdict?: string
  method?: string
}

export interface EvidenceDowPattern {
  target_dow?: number
  dow_label?: string
  hit_days?: number | null
  total_days?: number | null
  hit_rate?: number | null
  verdict?: string
  method?: string
}

export interface EvidenceMetrics {
  avg_delay_s?: number | null
  delay_index?: number | null
  saturation_rate?: number | null
  imbalance_index?: number | null
  avg_queue_m?: number | null
  max_queue_m?: number | null
  queue_storage_ratio_max?: number | null
  spillback_risk_max?: number | null
  level_of_service?: string | null
  level_of_service_label?: string | null
}

export interface EvidenceDirectionBreakdown {
  group: string
  focused?: boolean
  avg_queue_m?: number | null
  max_queue_m?: number | null
  avg_delay_s?: number | null
  queue_storage_ratio?: number | null
  saturation?: number | null
}

export interface EvidenceTurnBreakdown {
  label: string
  turn_saturation?: number | null
  green_utilization?: number | null
}

export interface EvidenceApproachBreakdown {
  link_id?: string
  dir8_label?: string
  stop_time_sec?: number | null
  stop_times?: number | null
  queue_len_est_m?: number | null
  delay_index?: number | null
}

export interface EvidenceLaneBreakdown {
  lane_id?: string
  link_id?: string
  label?: string
  lane_saturation?: number | null
  lane_flow?: number | null
  lane_capacity?: number | null
}

export interface TimingDeficitTurn {
  label: string
  green_time_plan?: number
  min_green_time?: number
  deficit_ratio?: number
  turn_saturation?: number | null
}

export interface RingDiagramRecord {
  cycle_len: number
  ring_count?: number
  pattern?: string
  green_times: number[]
  yellow_times: number[]
  red_times: number[]
  rings: Array<{ phases: number[]; barriers: number[] }>
  channel_info?: Array<Array<[number, number]>>
  follow_phase_info?: unknown[]
  offset_sec?: number | null
}

export interface RingDiagramPayload {
  available?: boolean
  reason?: string
  record?: RingDiagramRecord
}

export interface TimingProfile {
  cycle_length?: number
  cycle_issue?: string | null
  plan_count?: number
  period_count?: number
  plan_granularity_low?: boolean
  green_deficit_ratio_max?: number
  deficit_turns?: TimingDeficitTurn[]
  flow_green_fit?: {
    spearman_tau?: number | null
    verdict?: string
    narrative?: string
  }
  ring_diagram?: RingDiagramPayload
  narrative?: string
}

export interface CorridorNode {
  seq?: number
  inter_id?: string
  inter_name?: string
  is_current?: boolean
  lon?: number | null
  lat?: number | null
}

export interface CorridorContext {
  in_corridor?: boolean
  corridor_name?: string
  corridor_inter_count?: number
  inter_position?: number | null
  coord_cycle_sec?: number | null
  period_start_sec?: number | null
  period_end_sec?: number | null
  line_metrics?: Array<{
    line_name?: string
    delay_index?: number | null
    travel_speed_kmh?: number | null
    total_stop_times?: number | null
  }>
  corridor_nodes?: CorridorNode[]
  coord_stop_fwd?: number | null
  coord_stop_rev?: number | null
  avg_coord_stop_times?: number | null
  green_wave_break_risk?: boolean
  narrative?: string
}

export interface ExternalEvidence {
  complaint_total?: number
  complaints?: Array<{ type: string; count: number; sample?: string }>
  manual_survey?: Array<{ type: string; desc: string; level?: string }>
  field_survey?: Array<{ category: string; desc: string; severity?: string }>
  tags?: string[]
  has_external_evidence?: boolean
  narrative?: string
}

export interface DiagnosisStoryBeat {
  phase: string
  title: string
  text: string
}

export interface EvidenceThresholdsUsed {
  min_congested_days?: number
  window_days?: number
  excess_delay_s?: number
  long_queue_m?: number
  saturation_high?: number
  queue_storage_ratio_high?: number
}

export interface ProblemEvidence {
  inter_id?: string
  intersection?: string
  time_label?: string
  source_tier?: 'dwd_rolling_7d' | 'dws_weekday_pattern' | 'mock' | 'none' | string
  coverage_warning?: string | null
  target_dow?: number
  target_dow_label?: string
  summary?: string
  chronic?: EvidenceChronic
  dow_pattern?: EvidenceDowPattern
  metrics?: EvidenceMetrics
  by_direction?: EvidenceDirectionBreakdown[]
  by_turn?: EvidenceTurnBreakdown[]
  by_approach?: EvidenceApproachBreakdown[]
  by_lane?: EvidenceLaneBreakdown[]
  timing_profile?: TimingProfile
  corridor_context?: CorridorContext
  external_evidence?: ExternalEvidence
  diagnosis_story?: DiagnosisStoryBeat[]
  flow_trace?: FlowTrace | null
  thresholds_used?: EvidenceThresholdsUsed
  query_trace?: unknown[]
  reason?: string
}

export interface QuantitativeConstraintItem {
  metric: 'spillback_risk' | 'avg_queue_m' | 'saturation' | 'delta_seconds' | string
  scope: string
  operator: '<=' | '>=' | string
  value: number
  baseline?: number | null
  threshold_ref?: string | null
}

export type ConstraintIntent =
  | 'no_spillback'
  | 'no_queue_growth'
  | 'no_worsen'
  | 'saturation_cap'
  | 'protect'
  | string

export interface QuantitativeConstraints {
  raw_text: string
  intent?: ConstraintIntent
  primary_directions?: string[]
  protected_directions?: string[]
  constraints?: QuantitativeConstraintItem[]
  narrative?: string
}

export interface FlowTimingProblem {
  category: string
  label: string
  detected: boolean
  severity: string
  evidence: string[]
  governance: string
  matched_rule_ids?: string[]
  checklist_ref?: string
}

export interface FlowTimingExpertRule {
  id: string
  title: string
  text: string
  checklist_ref?: string
}

export type PrimaryDiagnosisType =
  | 'timing_optimizable'
  | 'capacity_bottleneck'
  | 'structure_limited'
  | 'basically_matched'

export interface TurnBalanceSide {
  label: string
  turn_saturation?: number | null
  green_utilization?: number | null
}

export interface TurnBalance {
  spare_util_threshold?: number
  over?: TurnBalanceSide
  spare?: TurnBalanceSide
}

export interface PrimaryDiagnosis {
  type: PrimaryDiagnosisType
  headline: string
  lever: string
  severity: 'high' | 'medium' | 'none'
  evidence: string[]
  structure_limited: boolean
  turn_balance?: TurnBalance
}

export interface FlowTraceSource {
  inter_id: string
  inter_name?: string | null
  feed_direction: string
  /** 路径途经率（%，非占比，多跳叠加可 >100） */
  path_coverage: number
  lng?: number | null
  lat?: number | null
}

export type FlowSourcePattern = 'single_corridor' | 'multi_corridor' | 'local'

export interface FlowTraceTurn {
  entry: string
  turn: string
  turn_saturation?: number | null
  source_pattern: FlowSourcePattern
  dominant_feed?: FlowTraceSource | null
  sources: FlowTraceSource[]
}

export interface FlowTraceGovernanceHint {
  type: 'upstream_coordination' | 'area_coordination' | string
  problem_turn?: string
  inter_id?: string
  inter_name?: string | null
  feed_direction?: string
  coverage?: number
  sources?: FlowTraceSource[]
}

export interface FlowTraceUpstreamMovement {
  turn: string
  cor_turn?: number
  feed_direction: string
  share_pct: number
  vehicles_of_100: number
  raw_coverage?: number
}

export interface FlowTraceEntry {
  entry: string
  dir8_code: number
  entry_max_saturation?: number | null
  upstream_inter_id: string
  upstream_inter_name?: string | null
  upstream_lng?: number | null
  upstream_lat?: number | null
  vehicles_base: number
  upstream_movements: FlowTraceUpstreamMovement[]
  dominant_movement?: FlowTraceUpstreamMovement | null
  narrative: string
}

export interface FlowTrace {
  available: boolean
  reason?: string
  period_type?: string
  day_basis?: string
  caveat?: string
  vehicles_base?: number
  entry_traces?: FlowTraceEntry[]
  problem_turns?: FlowTraceTurn[]
  governance_hints?: FlowTraceGovernanceHint[]
}

export interface GovernanceActionPlan {
  action_type?: string
  headline?: string
  narrative_template?: string
  transfer_seconds?: number
  cycle_unchanged?: boolean | null
  direction?: string
  upstream_inter_id?: string
  upstream_inter_name?: string
  upstream_movement?: string
  upstream_coverage?: number
  donor_turn?: {
    label?: string
    turn_saturation?: number
    green_utilization?: number
    green_sec?: number
    flow_share?: number
    green_share?: number
  }
  recipient_turn?: {
    label?: string
    turn_saturation?: number
    green_utilization?: number
    green_sec?: number
    flow_share?: number
    green_share?: number
  }
  confidence?: number
  evidence?: string[]
  data_gaps?: string[]
}

export interface FlowTimingGovernance {
  primary_diagnosis?: PrimaryDiagnosis
  /** 流量溯源补充建议（上游协同维度，独立于主诊断类型） */
  flow_trace_supplement?: string
  match_verdict: string
  match_narrative?: string
  flow_green_tau?: number | null
  summary?: string
  governance_narrative?: string
  problems?: FlowTimingProblem[]
  expert_rules?: FlowTimingExpertRule[]
  expert_rules_markdown?: string
  sustained_checklist?: Array<Record<string, unknown>>
  checklist_refs?: Record<string, string>
  data_gaps?: string[]
  action_plan?: GovernanceActionPlan
}

/** SSE step payload for problem_evidence */
export interface ProblemEvidenceSseData {
  summary?: string
  chronic?: EvidenceChronic
  dow_pattern?: EvidenceDowPattern
  metrics?: EvidenceMetrics
  by_turn?: EvidenceTurnBreakdown[]
  by_approach?: EvidenceApproachBreakdown[]
  timing_profile?: TimingProfile
  corridor_context?: CorridorContext
  external_evidence?: ExternalEvidence
  diagnosis_story?: DiagnosisStoryBeat[]
  flow_trace?: FlowTrace | null
}
