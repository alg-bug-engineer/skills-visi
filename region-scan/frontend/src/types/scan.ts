export type ProblemBand = '配时可解' | '工程可解' | '无明显问题' | '数据不足'

export interface ScanMetrics {
  saturation_max: number | null
  unbalance_index: number | null
  green_utilization: number | null
}

export interface GovernanceAction {
  category: string
  label: string
  severity: string
  governance: string
  evidence: string[]
}

export interface ScanRecord {
  inter_id: string
  inter_name: string
  lon: number | null
  lat: number | null
  period: string
  scene_type?: string | null
  pressure_level?: string | null
  metrics: ScanMetrics
  top_issues: string[]
  severity: string
  control_improvement_ceiling: string
  governance_summary: string
  governance_actions: GovernanceAction[]
  match_verdict?: string
  has_data: boolean
  data_quality_tags: string[]
  problem_band: ProblemBand
  pilot_score: number | null
  color_value?: number | null
}

export interface RunSummary {
  run_id: string
  created_at: string
  region: string
  periods: string[]
  intersection_total: number
  covered: number
}

export interface RunDetail extends RunSummary {
  metric: string | null
  records: ScanRecord[]
}

export interface PilotsResponse {
  run_id: string
  count: number
  pilots: ScanRecord[]
}

export type MetricKey = 'saturation_max' | 'unbalance_index' | 'green_utilization'
export type ColorMode = 'band' | MetricKey
