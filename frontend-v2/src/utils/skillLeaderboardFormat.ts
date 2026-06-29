import type { SkillLeaderboardItem } from '../types/skillLeaderboard'

const PROBLEM_LABELS: Record<string, string> = {
  congestion: '拥堵',
}

export function problemTypeLabel(problemType: string): string {
  return PROBLEM_LABELS[problemType] ?? problemType
}

export function formatLeaderboardTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function skillChips(item: SkillLeaderboardItem): string[] {
  const match = item.tags.match ?? {}
  const chips = [
    item.time_period_label || match.time_period,
    problemTypeLabel(item.problem_type || match.problem_type || ''),
    ...(match.directions ?? []).slice(0, 2),
  ].filter(Boolean) as string[]
  return chips.slice(0, 4)
}

export function contributorLabel(item: SkillLeaderboardItem): string {
  const meta = item.tags.meta ?? {}
  const role = meta.contributor_role?.trim()
  if (role) return role
  return '系统沉淀'
}

export function experienceSourceLabel(item: SkillLeaderboardItem): string {
  const source = item.tags.meta?.experience_source
  if (source === 'field_officer') return '现场经验'
  return source ?? '—'
}
