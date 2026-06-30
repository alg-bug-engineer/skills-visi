// 三级经验沉淀与专家案例经验（对应后端 meta.reused_experience / meta.case_experience
// 与 SSE experience_cognition/diagnosis/solution 步骤）。

export type ExperienceLevel = 'cognition' | 'diagnosis' | 'solution'

export interface ExperienceSedimentItem {
  level: ExperienceLevel
  text: string
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
