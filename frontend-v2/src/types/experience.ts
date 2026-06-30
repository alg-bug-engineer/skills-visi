// 三级经验沉淀与专家案例经验（对应后端 meta.reused_experience / meta.case_experience
// 与 SSE experience_cognition/diagnosis/solution 步骤）。

export type ExperienceLevel = 'cognition' | 'diagnosis' | 'solution'

export interface ExperienceSedimentItem {
  level: ExperienceLevel
  text: string
  /** 仅 cognition（认知画像）使用：数据支撑则已验证，否则待验证。 */
  status?: 'verified' | 'pending'
  /** 展示用标签（问题记录 / 用户口述 / 治理措施等） */
  tags?: string[]
}

export interface CaseSolution {
  name: string
  measures?: string[]
  applicability?: string
  caution?: string
}

export interface CaseProblem {
  problem: string
  solutions: CaseSolution[]
}

export interface CaseScenario {
  scenario_id: string
  scenario_name: string
  description?: string
  problems: CaseProblem[]
}

/* ── 经验库三桶（/experience/library 响应） ───────────────────────────── */

export interface ExperienceCognitionItem {
  inter_id: string
  text: string
  status: 'verified' | 'data_doubt' | 'manual' | string
  source: string
  evidence?: Record<string, unknown>
  ts: string
}

export interface ExperienceDiagnosisItem {
  inter_id: string
  cause: string
  dimension: string
  scope?: string | null
  source: string
  confidence: number
  ts: string
}

export interface ExperienceSolutionItem {
  inter_id: string
  skill_id: string
  qualitative?: string | null
  quantified?: string | null
  ts: string
  intersection?: string
  time_period_label?: string
  solution_measure?: string | null
  download_url?: string | null
}

export interface ExperienceLibrary {
  inter_id?: string | null
  cognition: ExperienceCognitionItem[]
  diagnosis: ExperienceDiagnosisItem[]
  solution: ExperienceSolutionItem[]
}

/* ── 案例库（/cases/industry 与 /cases/intersections） ─────────────────── */

export interface RepresentativeCase {
  id: string
  title: string
  snippet: string
}

export interface IndustryCaseSolution {
  name: string
  frequency: number
  measures: string[]
  applicability: string
  caution: string
  representative_cases: RepresentativeCase[]
}

export interface IndustryCaseProblem {
  problem: string
  occurrence: number
  symptoms: string[]
  solutions: IndustryCaseSolution[]
}

export interface IndustryCaseScenario {
  scenario_id: string
  scenario_name: string
  description: string
  case_count: number
  problems: IndustryCaseProblem[]
}

export interface IntersectionCaseSolution {
  skill_id: string
  qualitative?: string | null
  quantified?: string | null
  solution_measure?: string | null
  download_url?: string | null
  ts: string
}

export interface IntersectionCase {
  inter_id: string
  intersection: string
  time_period_label: string
  cognition: ExperienceCognitionItem[]
  diagnosis: ExperienceDiagnosisItem[]
  solutions: IntersectionCaseSolution[]
  ts: string
}

/** 治理建议溯源依据（对应后端 SuggestionReference）。 */
export interface SuggestionReference {
  type: 'industry' | 'intersection' | string
  id: string
  title: string
  summary?: string
  scenario_id?: string | null
}
