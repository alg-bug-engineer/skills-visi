export type SeverityLevel = 'high' | 'medium' | 'low' | 'unknown'

/** 复刻后端 map_presentation_service._severity 阈值口径。 */
export function severityLevel(sat: number | null | undefined): SeverityLevel {
  if (sat == null || Number.isNaN(sat)) return 'unknown'
  if (sat >= 0.85) return 'high'
  if (sat >= 0.65) return 'medium'
  return 'low'
}

/** 饱和度 → 颜色（与既有 severityColor 一致；unknown 取暗底色）。 */
export function severityColor(sat: number | null | undefined): string {
  switch (severityLevel(sat)) {
    case 'high':
      return '#ff6b4a'
    case 'medium':
      return '#ffaa44'
    case 'low':
      return '#6dffb5'
    default:
      return '#3a4a66'
  }
}
