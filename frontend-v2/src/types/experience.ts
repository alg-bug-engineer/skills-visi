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
