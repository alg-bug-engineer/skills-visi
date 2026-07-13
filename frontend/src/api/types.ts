/**
 * 后端公开响应类型（镜像 docs/剧本字段-API对照.md 与真实响应）。
 * 约定：可能缺失/为空的字段一律 `| null` 或可选，前端做守卫降级。
 */

import type { EvidenceChip, ValueSnapshot } from '@/types/skillAbsorption'
import type { SkillBuildStage } from '@/types/skillBuild'

export type LngLat = [number, number]

export interface MatchCandidate {
  inter_id: string | null
  inter_name: string | null
  confidence: number | null
  source: string | null
}

export interface UserExperience {
  experience_type: string
  content: string
  source_span?: string | null
  tags?: Record<string, unknown>
}

export interface DiagnosisTicket {
  object_type: string | null
  intersection_name: string | null
  intersection_name_candidates?: string[]
  inter_id: string | null
  lng: number | null
  lat: number | null
  time_range: string | null
  period: string | null
  direction: string | null
  movement: string | null
  problem_type: string | null
  constraints: string[]
  diagnosis_scope: string | null
  governance_goal: string | null
  match_confidence: number | null
  match_method: string | null
  match_candidates?: MatchCandidate[]
  user_experiences?: UserExperience[]
}

export interface RecognitionStep {
  step: string
  status: string
  label: string
}

export interface SpatialNode {
  inter_id?: string | null
  inter_name?: string | null
  lng?: number | null
  lat?: number | null
  [k: string]: unknown
}

export interface SpatialScene {
  available: boolean
  recognition_steps: RecognitionStep[]
  target: {
    inter_id: string | null
    inter_name: string | null
    lng: number | null
    lat: number | null
    direction: string | null
    movement: string | null
  } | null
  highlight_path: LngLat[]
  upstream_nodes: SpatialNode[]
  downstream_nodes: SpatialNode[]
  main_path?: string | null
  axis_roads?: {
    ew_road?: string | null
    ns_road?: string | null
    available?: boolean
    source?: string
  }
}

export interface SpatialObjects {
  target_intersection?: string
  target_direction?: string
  target_movement?: string
  upstream_scope?: string
  downstream_scope?: string
  main_path?: string
}

export interface IntentPhase {
  diagnosis_ticket?: DiagnosisTicket
  spatial_scene?: SpatialScene
  spatial_objects?: SpatialObjects
  user_experiences?: UserExperience[]
}

/** 逐进口富指标（analyze_overflow.build_by_approach）。源缺失即空列表。 */
export interface ApproachMetric {
  approach: string
  saturation: number | null
  delay_index: number | null
  los: string | null
}

/** 逐转向富指标（analyze_overflow.build_by_movement）。level ∈ 过饱和/偏高/正常/null。 */
export interface MovementMetric {
  movement: string
  saturation: number | null
  green_utilization: number | null
  level: string | null
}

export interface Metrics {
  queue_length_m: number | null
  storage_length_m: number | null
  queue_ratio: number | null
  saturation?: number | null
  saturation_rate?: number | null
  los?: string | null
  green_utilization: number | null
  stop_count: number | null
  avg_delay_s: number | null
  time_series_trend: string | null
  // 需求13：运行数据卡富指标（可选，源缺失即缺省/空列表，前端守卫降级）
  by_approach?: ApproachMetric[]
  by_movement?: MovementMetric[]
  imbalance_index?: number | null
  approach_count?: number | null
  lane_count?: number | null
  [k: string]: unknown
}

export interface OverflowVerification {
  verified: boolean | null
  risk_level: string | null
  message: string | null
}

export interface DownstreamNodeMetrics {
  saturation?: number | null
  saturation_rate?: number | null
  level_of_service?: string | null
  queue_storage_ratio_max?: number | null
  green_utilization?: number | null
  [k: string]: unknown
}

export interface DownstreamTurnMetric {
  label?: string | null
  turn_saturation?: number | null
  green_utilization?: number | null
  queue_ratio?: number | null
  flow_vph?: number | null
}

export interface PrimaryDownstream {
  inter_id?: string | null
  inter_name?: string | null
  metrics?: DownstreamNodeMetrics
  by_turn?: DownstreamTurnMetric[]
  remaining_storage_m?: number | null
  capacity?: {
    can_release?: boolean
    blocked?: boolean
    reasons?: string[]
    release_guard?: string
  }
}

export interface DownstreamDiagnosis {
  available?: boolean
  scenario: string | null
  release_answer: string | null
  narrative?: string | null
  judgment_criteria?: Record<string, boolean>
  primary_downstream?: PrimaryDownstream
  can_simple_add_green: boolean | null
  expert_question?: string | null
  [k: string]: unknown
}

export interface ArterialAnalysis {
  upstream_arrival_flow_vph: number | null
  upstream_release_intensity_vph: number | null
  target_remaining_storage_m: number | null
  downstream_remaining_storage_m?: number | null
  downstream_remaining_capacity?: string | null
  phase_offset_match: string | null
  need_upstream_metering: boolean | null
  need_downstream_dissipation_first: boolean | null
  summary: string | null
  [k: string]: unknown
}

export interface CoordinationNode {
  inter_id: string | null
  inter_name?: string | null
  lng?: number | null
  lat?: number | null
  role: 'upstream' | 'target' | 'downstream'
  spacing_m: number | null
  spacing_source?: string | null
  offset_abs_s: number | null
  offset_source?: string | null
  phase_diff_s: number | null
  travel_speed_kmh: number | null
  travel_time_s: number | null
  travel_source?: string | null
}

export interface Coordination {
  available: boolean
  reason?: string
  direction?: 'inbound' | 'outbound' | 'bidirectional' | 'unknown'
  cycle_s?: number | null
  source?: string | null
  target?: { inter_id?: string | null; inter_name?: string | null; lng?: number | null; lat?: number | null }
  nodes?: CoordinationNode[]
}

export interface MapSceneTurnTrace {
  movement?: string | null
  name?: string | null
  share_pct?: number | null
  path?: LngLat[]
  lon?: number | null
  lat?: number | null
  trace_kind?: string | null
  [k: string]: unknown
}

export interface MapScene {
  action?: string
  phase?: string
  available?: boolean
  center?: LngLat | null
  trace_direction?: string
  turn_traces?: MapSceneTurnTrace[]
  adjacent_intersections?: Array<{
    inter_id?: string | null
    inter_name?: string | null
    lng?: number | null
    lat?: number | null
    metrics?: Record<string, unknown>
  }>
  /** 需求 33：路段覆盖溯源 */
  target?: {
    id?: string
    name?: string
    lng?: number | null
    lat?: number | null
    target_flow?: number
    direction?: string
    [k: string]: unknown
  }
  intersections?: Array<{
    id?: string
    name?: string
    lng?: number | null
    lat?: number | null
    rank?: number
    flow?: number
    ratio?: number
    [k: string]: unknown
  }>
  links?: Array<{
    id?: string
    name?: string
    coords?: LngLat[]
    rank?: number
    flow?: number
    ratio?: number
    [k: string]: unknown
  }>
  [k: string]: unknown
}

/** 配时概览（analyze_overflow.build_timing_profile）。字段可能缺失为 null。 */
export interface TimingProfile {
  cycle_s: number | null
  time_plan_count: number | null
  plan_name: string | null
}

/** 问题规律（analyze_overflow.derive_problem_regularity，派生非实测）。basis 恒有值。 */
export interface ProblemRegularity {
  recurring: string | null
  periodic: string | null
  basis: string
}

export interface DiagnosisPhase {
  metrics?: Metrics
  // 需求13：配时概览 + 问题规律（可选，缺失即降级不展示）
  timing_profile?: TimingProfile | null
  problem_regularity?: ProblemRegularity | null
  downstream_metrics?: Record<string, unknown>
  overflow_verification?: OverflowVerification
  downstream_diagnosis?: DownstreamDiagnosis
  bottleneck_analysis?: { bottleneck_type?: string | null; [k: string]: unknown }
  arterial_analysis?: ArterialAnalysis
  coordination?: Coordination
  flow_trace?: { entry_traces?: MapSceneTurnTrace[]; [k: string]: unknown }
  map_scenes?: Record<string, MapScene>
  scenario_report?: {
    available?: boolean
    issues?: Array<{ item_id: string; label: string; status: string; summary?: string }>
    [k: string]: unknown
  }
  problem_confirmed?: boolean
  /** 健康核验：路口无问题时为 true，闭环在诊断后正常收尾。 */
  healthy?: boolean
  data_source?: string
  [k: string]: unknown
}

export interface CaseCard {
  case_id?: string
  title?: string
  similarity?: number | null
  similarity_points?: string[]
  similarity_dimensions?: Array<{ key?: string; label?: string }>
  transferable_actions?: string[]
  caveats?: string[]
  help_summary?: string
  similarity_tier?: 'high' | 'matched' | string
  structured_tags?: Record<string, string[]>
  dimension_scores?: Record<string, number>
  action?: string
  historical_action?: string
  outcome?: string
  lesson?: string
  case_type?: string
  score?: number
  [k: string]: unknown
}

export interface CausePhase {
  cause_analysis?: {
    primary_cause?: string
    secondary_causes?: string[]
    optimizable_points?: string[]
    data_gaps?: string[]
    narrative?: string
  }
  cause_scores?: Record<string, number>
  cause_ranking?: Array<{ rank?: number; cause?: string; role?: string }>
  case_cards?: {
    matched_count?: number
    high_similarity_count?: number
    cards?: CaseCard[]
  }
  arterial_coordination_needed?: boolean
  [k: string]: unknown
}

/** 治理策略「参考依据」（select_package.build_reference_basis）。industry_scene 缺依据即 null。 */
export interface ReferenceBasis {
  industry_scene: string | null
  intersection_case_ids: string[]
}

export interface ExperienceContrastRef {
  type?: string
  record_id?: string
  trace_id?: string
  case_id?: string
  label?: string
}

export interface ExperienceContrastItem {
  dimension?: string
  without_experience?: { summary?: string; source?: string; refs?: ExperienceContrastRef[] }
  with_experience?: { summary?: string; source?: string; refs?: ExperienceContrastRef[] }
}

export interface ExperienceContrast {
  available?: boolean
  reason?: string | null
  items?: ExperienceContrastItem[]
}

export interface StrategyPhase {
  strategy?: {
    principles?: string[]
    recommended?: string[]
    not_recommended?: string[]
    hard_constraints?: string[]
    coordination_scope?: string
    trigger_exit_rules?: Record<string, unknown>
  }
  strategy_package?: string
  // 需求13：治理策略卡「参考依据」（可选，缺失即降级不展示）
  reference_basis?: ReferenceBasis | null
  control_scope_map?: MapScene & {
    target_intersection?: { inter_id?: string; inter_name?: string; lng?: number; lat?: number }
    upstream_metering_points?: Array<Record<string, unknown>>
    downstream_protection_nodes?: Array<Record<string, unknown>>
    coordination_paths?: Array<{ path?: [number, number][]; inter_name?: string; role?: string }>
  }
  experience_contrast?: ExperienceContrast
  case_references?: Record<string, unknown>
  [k: string]: unknown
}

export interface PhaseStageTiming {
  phase_stage_id: string
  phase_stage_name: string
  green_time_s: number
  yellow_time_s: number
  all_red_time_s: number
  min_green_time_s?: number
  max_green_time_s?: number
  split_ratio?: number
  phase_saturation?: number | null
  current_timing?: StageTimingPart | null
  optimized_timing?: StageTimingPart | null
  green_delta_s?: number | null
  stage_delta_s?: number | null
  movements?: StageMovement[]
  [k: string]: unknown
}

export interface StageMovement {
  movement_key?: string | null
  movementKey?: string | null
  label?: string | null
  dir8No?: number | null
  turnDirNo?: number | null
  turnFlowTotal?: number | null
  laneCount?: number | null
  saturation?: number | null
  flow_available?: boolean | null
  source?: string | null
  historyVirtualFlowVph?: number | null
}

export interface StageTimingPart {
  green_time_s?: number | null
  yellow_time_s?: number | null
  all_red_time_s?: number | null
  stage_total_s?: number | null
}

export interface DirectionIntensity {
  movementKey?: string | null
  label?: string | null
  dir8No?: number | null
  turnDirNo?: number | null
  intensity?: number | null
  flow_source?: string | null
  historyVirtualFlowVph?: number | null
}

export interface OptimizationMeta {
  solver?: string | null
  target_saturation?: number | null
  max_phase_saturation?: number | null
  total_turn_flow_vph?: number | null
  target_periods?: string[]
  period_plan_no?: string | null
  period_label?: string | null
  period_match_method?: string | null
  direction_intensity_list?: DirectionIntensity[]
  notes?: string[]
  data_quality?: Record<string, unknown>
}

export interface PlanTimingEvidence {
  available?: boolean | null
  reason?: string | null
  missing_fields?: string[]
  current_cycle_s?: number | null
  cycle_s?: number | null
  cycle_delta_s?: number | null
  phase_stage_timing_list?: PhaseStageTiming[]
  meta?: OptimizationMeta | null
}

export interface PlanCandidate {
  plan_id: string
  name: string
  status: string
  scenario?: string
  case_basis?: { matched_cases?: number; lesson?: string }
  timing?: PlanTimingEvidence
  upstream_control?: { enabled?: boolean; control_points?: unknown[] }
  phase_offset_sec?: number
  pedestrian_constraints?: { satisfied?: boolean; violations?: string[] }
  downstream_risk?: { level?: string; reasons?: string[] }
  expected_effect?: string
  risk?: string
  rollback_condition?: string
  execution_order?: string[]
  guardrail_pass?: boolean
  validation_errors?: string[]
  // 设计稿提及但后端当前未透出（附录 B），可选：
  vc_predictions?: Record<string, number>
  [k: string]: unknown
}

export interface PlanBlock {
  candidates: PlanCandidate[] | null
  recommended: PlanCandidate | null
  recommendation: {
    recommended_plan_id?: string
    rationale?: string
  } | null
  rollback_conditions: string[] | null
  signal_source: string | null
  optimizer_engine: string | null
  all_guardrails_passed: boolean | null
}

export interface PhaseResult {
  phase: string
  success: boolean
  duration_ms: number | null
  errors: string[]
}

export interface RunResponse {
  trace_id: string | null
  completed: boolean | null
  pipeline_complete: boolean
  diagnosis_ticket: DiagnosisTicket | null
  phases: {
    intent?: IntentPhase
    diagnosis?: DiagnosisPhase
    cause?: CausePhase
    strategy?: StrategyPhase
    plan?: Record<string, unknown>
  }
  plan: PlanBlock | null
  phase_results: PhaseResult[]
}

export interface HealthResponse {
  status: string
  llm_mock: boolean
  model: string
  pg_configured: boolean
}

// ── 需求14：技能固化（经验吸收 + 构建落盘）响应契约 ─────────────────────────
// 契约以真实后端响应为准（frontend/src/mock/skill_solidify_fixture.json）。

/** 构建阶段 key（对齐 SkillBuildStage 非终态子集）。 */
export type SkillStage = Exclude<SkillBuildStage, 'idle' | 'completed' | 'failed'>

/** build.stages 单项：进度由响应驱动。 */
export interface SkillBuildStageInfo {
  key: SkillStage
  label: string
  progress: number
}

/** build.files 单项：真实文件内容。 */
export interface SkillFile {
  path: string
  name: string
  language: string
  content: string
}

/** absorption.stages 单项：6 阶段真实证据。 */
export interface AbsorptionStageInfo {
  key: string
  label: string
  monologue: string
  evidence_chips: EvidenceChip[]
  duration_ms: number
}

/** 技能标签：来自真实 ticket/strategy/plan。 */
export interface SkillTags {
  match: Record<string, unknown>
  content: Record<string, unknown>
  meta: Record<string, unknown>
}

/** POST /agent/skill/solidify 响应。download_url 已含 /api/v1 前缀，勿再拼接。 */
export interface SkillSolidificationResult {
  action: 'created' | 'updated' | 'unchanged'
  skill_id: string
  skill_dir: string
  download_url: string
  intersection: string | null
  inter_id: string | null
  time_period_label: string | null
  tags: SkillTags
  trace_id: string
  plan_id: string
  absorption: {
    action: 'CREATE' | 'UPDATE' | 'UNCHANGED'
    stages: AbsorptionStageInfo[]
    value_snapshot: ValueSnapshot
  }
  build: {
    stages: SkillBuildStageInfo[]
    files: SkillFile[]
  }
}

export interface ApiError {
  ok: false
  reason: string
  detail?: unknown
}
