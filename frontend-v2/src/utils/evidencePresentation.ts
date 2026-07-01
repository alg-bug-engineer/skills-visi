import type { ProblemEvidence, QuantitativeConstraintItem } from '../types/evidence'
import type { CognitionPayload, IntersectionLink, MapSceneMarker } from '../types/map'
import { THRESHOLDS } from '../constants'
import { isEntrance, linkSegmentAnchor, normalizeDir } from './mapMarkers'

/** 绿灯利用率：与数仓原值一致，不做 ×100 百分比换算。 */
export function formatGreenUtilizationRaw(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

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
    // 关注方向分向卡与渠化/转向饱和度重复，不在地图上重复落标。
    if (row.focused) continue
    const group = row.group
    const dirs = highlightDirsForGroup(group)
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
    const dirs = highlightDirsForGroup(group)
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

/** 与 backend/intersection_agent/utils/direction_groups.py GROUP_TO_DIRS 对齐 */
export const GROUP_TO_DIRS: Record<string, string[]> = {
  东西向: ['东', '西'],
  南北向: ['南', '北'],
  东南向: ['东南'],
  西南向: ['西南'],
  东北向: ['东北'],
  西北向: ['西北'],
}

export const AXIS_FOCUS_GROUPS = ['东西向', '南北向'] as const

/** 将任意方向标签归一为东西向/南北向轴对名。 */
export function toAxisFocusGroup(label: string): (typeof AXIS_FOCUS_GROUPS)[number] | null {
  const trimmed = label.replace(/进口/g, '').trim()
  if (trimmed === '东西' || trimmed === '东西向' || trimmed === '东' || trimmed === '西') return '东西向'
  if (trimmed === '南北' || trimmed === '南北向' || trimmed === '南' || trimmed === '北') return '南北向'
  if (GROUP_TO_DIRS['东西向']?.includes(trimmed)) return '东西向'
  if (GROUP_TO_DIRS['南北向']?.includes(trimmed)) return '南北向'
  return null
}

/** 关注方向只能是东西向或南北向之一，禁止两轴同时关注或四向拆分。 */
export function normalizeAxisFocusGroups(groups: string[]): string[] {
  const axis: string[] = []
  for (const g of groups) {
    const canonical = toAxisFocusGroup(g) ?? (GROUP_TO_DIRS[g] ? g : null)
    if (canonical && AXIS_FOCUS_GROUPS.includes(canonical as (typeof AXIS_FOCUS_GROUPS)[number])) {
      if (!axis.includes(canonical)) axis.push(canonical)
    }
  }
  return axis.length > 1 ? [axis[0]] : axis
}

const OBLIQUE_TO_CARDINAL: Record<string, string> = {
  东南: '东',
  东北: '东',
  西南: '西',
  西北: '西',
  东: '东',
  西: '西',
  南: '南',
  北: '北',
}

export function highlightDirsForGroup(group: string): string[] {
  const canonical = GROUP_TO_DIRS[group]
  if (canonical) return [...canonical]
  const trimmed = group.replace(/向$/, '').trim()
  if (trimmed.length === 1 && '东西南北'.includes(trimmed)) return [trimmed]
  const withSuffix = `${trimmed}向`
  if (GROUP_TO_DIRS[withSuffix]) return [...GROUP_TO_DIRS[withSuffix]]
  return []
}

/** 将分向组展开为地图高亮方向（去重，禁止按字符拆分复合方向名）。 */
export function expandFocusGroupsToHighlightDirs(groups: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const group of groups) {
    for (const dir of highlightDirsForGroup(group)) {
      if (!seen.has(dir)) {
        seen.add(dir)
        out.push(dir)
      }
    }
  }
  return out
}

/** 斜向/分向标签 → 渠化四臂（东/南/西/北），供臂标与 role 高亮。 */
export function toCardinalArmDirs(dirs: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of dirs) {
    const token = raw.replace(/进口/g, '').replace(/向$/g, '').trim()
    const card = OBLIQUE_TO_CARDINAL[token]
    if (card && !seen.has(card)) {
      seen.add(card)
      out.push(card)
    }
  }
  return out
}

export function linksForDirs(links: IntersectionLink[], groups: string[]): string[] {
  const dirs = expandFocusGroupsToHighlightDirs(groups)
  return links
    .filter(
      (l) =>
        isEntrance(l.link_role) &&
        dirs.some((d) => normalizeDir(l.dir4_label || '').includes(normalizeDir(d))),
    )
    .map((l) => l.link_id)
}
