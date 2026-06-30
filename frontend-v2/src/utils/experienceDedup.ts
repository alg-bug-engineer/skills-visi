import type { ExperienceLevel, ExperienceSedimentItem } from '../types/experience'

/** 经验文本归一化，用于跨来源去重（沉淀 vs 复用 badge）。 */
export function normalizeExperienceText(text: string): string {
  return text
    .replace(/^复用了\s+\S+\s+的[^：:]+[：:]\s*/u, '')
    .replace(/\s+/g, '')
    .replace(/[，。；、]/g, '')
    .toLowerCase()
}

export function experienceDedupKey(level: ExperienceLevel, text: string): string {
  return `${level}:${normalizeExperienceText(text)}`
}

/** 同 level + 归一化文本去重，保留先出现的条目。 */
export function dedupeExperienceSediment(
  items: ExperienceSedimentItem[],
): ExperienceSedimentItem[] {
  const seen = new Set<string>()
  const out: ExperienceSedimentItem[] = []
  for (const item of items) {
    const key = experienceDedupKey(item.level, item.text)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

/** 经验复用 badge 若与已沉淀正文重复则隐藏。 */
export function filterReusedExperienceBadges(
  reused: string[],
  sediment: ExperienceSedimentItem[],
): string[] {
  const sedimentNorm = new Set(
    sediment.map((s) => normalizeExperienceText(s.text)).filter(Boolean),
  )
  return reused.filter((badge) => {
    const core = normalizeExperienceText(badge)
    if (!core) return false
    for (const norm of sedimentNorm) {
      if (core.includes(norm) || norm.includes(core)) return false
    }
    return true
  })
}
