import { describe, expect, it } from 'vitest'
import type { SkillLeaderboardItem } from '../types/skillLeaderboard'
import {
  contributorLabel,
  formatLeaderboardTime,
  problemTypeLabel,
  skillChips,
} from './skillLeaderboardFormat'

function sampleItem(overrides: Partial<SkillLeaderboardItem> = {}): SkillLeaderboardItem {
  return {
    skill_id: 'skill_test',
    skill_dir: 'congestion-test-evening-peak',
    intersection: '测试路口',
    inter_id: 'inter_test',
    problem_type: 'congestion',
    time_period_label: '晚高峰',
    rule_ids: ['R1'],
    created_at: '2026-06-20T08:00:00+00:00',
    updated_at: null,
    hit_count: 3,
    last_hit_at: null,
    tags: {
      match: { directions: ['南北向'], problem_type: 'congestion' },
      meta: { contributor_role: '一线民警', experience_source: 'field_officer' },
    },
    user_constraints: null,
    suggestion_formula: 'min(x, 20)',
    download_url: '/api/v1/skills/skill_test/download',
    ...overrides,
  }
}

describe('skillLeaderboardFormat', () => {
  it('maps problem type label', () => {
    expect(problemTypeLabel('congestion')).toBe('拥堵')
    expect(problemTypeLabel('custom')).toBe('custom')
  })

  it('builds chip row from item fields', () => {
    expect(skillChips(sampleItem())).toEqual(['晚高峰', '拥堵', '南北向'])
  })

  it('formats contributor from meta', () => {
    expect(contributorLabel(sampleItem())).toBe('一线民警')
    expect(contributorLabel(sampleItem({ tags: {} }))).toBe('系统沉淀')
  })

  it('formats invalid time gracefully', () => {
    expect(formatLeaderboardTime(null)).toBe('—')
    expect(formatLeaderboardTime('not-a-date')).toBe('not-a-date')
  })
})
