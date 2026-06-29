export type SkillLeaderboardSort = 'hits' | 'created' | 'updated'

export interface SkillLeaderboardTags {
  match?: {
    intersection?: string
    inter_id?: string
    time_period?: string
    problem_type?: string
    directions?: string[]
    match_keywords?: string[]
  }
  content?: {
    rule_ids?: string[]
    issue_codes?: string[]
    constraint_intent?: string
    has_user_constraints?: boolean
    suggestion_formula_hash?: string
    data_window_profile?: string
  }
  meta?: {
    experience_source?: string
    contributor_role?: string
    source_utterance_summary?: string
    version?: number
    hit_count?: number
    last_hit_at?: string
  }
}

export interface SkillLeaderboardItem {
  skill_id: string
  skill_dir: string
  intersection: string
  inter_id: string
  problem_type: string
  time_period_label: string
  rule_ids: string[]
  created_at: string
  updated_at: string | null
  hit_count: number
  last_hit_at: string | null
  tags: SkillLeaderboardTags
  user_constraints: string | null
  suggestion_formula: string
  download_url: string
}
