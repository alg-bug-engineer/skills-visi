import type { ProblemEvidence, QuantitativeConstraintItem } from '../types/evidence'
import type { CognitionPayload, IntersectionLink, MapSceneMarker } from '../types/map'
import { THRESHOLDS } from '../constants'
import { isEntrance, linkSegmentAnchor, normalizeDir } from './mapMarkers'

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** 饱和度统一用小数表示，如 0.92、1.50 */
export function formatSaturation(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

export function formatMetricValue(metric: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (metric.includes('risk') || metric === 'saturation' || metric === 'queue_storage_ratio') {
    return value.toFixed(2)
  }
  if (metric.includes('queue')) return `${value.toFixed(1)}m`
  if (metric.includes('delay')) return `${value.toFixed(0)}s`
  return String(value)
}

export function metricLabel(metric: string): string {
  const map: Record<string, string> = {
    spillback_risk: '溢流风险',
    avg_queue_m: '平均排队',
    saturation: '饱和度',
    delta_seconds: '绿灯调整',
    queue_storage_ratio: '排队/储车比',
  }
  return map[metric] ?? metric
}

export function sourceTierLabel(tier?: string | null): string {
  const map: Record<string, string> = {
    dwd_rolling_7d: '近7日明细',
    dws_weekday_pattern: '周模式',
    mock: '演示数据',
    none: '无数据',
  }
  return map[tier ?? ''] ?? tier ?? '—'
}

export function constraintProgress(item: QuantitativeConstraintItem): {
  baseline: number
  cap: number
  pct: number
} {
  const baseline = item.baseline ?? 0
  const cap = item.value
  const pct = Math.min(100, Math.max(0, (baseline / Math.max(cap, 0.001)) * 100))
  return { baseline, cap, pct }
}

/** 从 problem_evidence 生成分向地图 Marker */
export function buildEvidenceDirectionMarkers(
  evidence: ProblemEvidence,
  cognition: CognitionPayload | null,
): MapSceneMarker[] {
  if (!cognition?.intersection) return []
  const center: [number, number] = [cognition.intersection.lon, cognition.intersection.lat]
  const links = cognition.links ?? []
  const markers: MapSceneMarker[] = []

  for (const row of evidence.by_direction ?? []) {
    const group = row.group
    const dirs = group.replace('向', '').split('').filter(Boolean)
    const link = links.find(
      (l) =>
        isEntrance(l.link_role) &&
        dirs.some((d) => normalizeDir(l.dir4_label || '').includes(d)),
    )
    if (!link) continue
    const [lon, lat] = linkSegmentAnchor(link, center)
    const sat = row.saturation
    const queue = row.avg_queue_m
    const severity =
      sat != null && sat >= THRESHOLDS.saturationHigh
        ? 'high'
        : sat != null && sat >= 0.65
          ? 'medium'
          : 'low'
    markers.push({
      id: `evidence-dir-${group}`,
      lon,
      lat,
      kind: row.focused ? 'metric' : 'evidence',
      variant: row.focused ? 'saturation' : 'evidence',
      title: group,
      value: sat != null ? formatSaturation(sat) : queue != null ? `${queue.toFixed(0)}m` : '—',
      subtitle: row.focused ? '关注方向' : '分向指标',
      severity,
      dir: normalizeDir(link.dir4_label || ''),
      link_id: link.link_id,
    })
  }
  return markers
}

export function buildProtectedDirectionMarkers(
  protectedDirs: string[],
  cognition: CognitionPayload | null,
  constraints: QuantitativeConstraintItem[],
): MapSceneMarker[] {
  if (!cognition?.intersection || !protectedDirs.length) return []
  const center: [number, number] = [cognition.intersection.lon, cognition.intersection.lat]
  const links = cognition.links ?? []
  const markers: MapSceneMarker[] = []

  for (const group of protectedDirs) {
    const constraint = constraints.find((c) => c.scope === group)
    const dirs = group.replace('向', '').split('').filter(Boolean)
    const link = links.find(
      (l) =>
        isEntrance(l.link_role) &&
        dirs.some((d) => normalizeDir(l.dir4_label || '').includes(d)),
    )
    if (!link) continue
    const [lon, lat] = linkSegmentAnchor(link, center)
    markers.push({
      id: `protect-${group}`,
      lon,
      lat,
      kind: 'evidence',
      variant: 'protected',
      title: `${group}·保护`,
      value: constraint ? `≤${formatMetricValue(constraint.metric, constraint.value)}` : '保护',
      subtitle: constraint
        ? `现状 ${formatMetricValue(constraint.metric, constraint.baseline ?? 0)}`
        : '约束边界',
      severity: 'low',
      dir: normalizeDir(link.dir4_label || ''),
      link_id: link.link_id,
    })
  }
  return markers
}

export function highlightDirsForGroup(group: string): string[] {
  return group.replace('向', '').split('').filter(Boolean)
}

export function linksForDirs(links: IntersectionLink[], groups: string[]): string[] {
  const dirs = groups.flatMap((g) => highlightDirsForGroup(g))
  return links
    .filter(
      (l) =>
        isEntrance(l.link_role) &&
        dirs.some((d) => normalizeDir(l.dir4_label || '').includes(normalizeDir(d))),
    )
    .map((l) => l.link_id)
}
