import { TA_THEME } from '../theme'
import type { CognitionPayload, IntersectionLink, MapActionEvent, MapSceneMarker } from '../types/map'

export function normalizeDir(label: string): string {
  const text = String(label || '').replace(/进口|出口/g, '').trim()
  for (const key of ['东北', '东南', '西北', '西南', '东', '西', '南', '北']) {
    if (text.includes(key)) return key
  }
  return text
}

export function isEntrance(role: string) {
  return role === 'entrance' || role === '进口'
}

function dist2(a: [number, number], b: [number, number]) {
  return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
}

/**
 * 锚点落在进口道停线附近的路段上（沿 link 折线向内一步），不推到外围边框。
 */
export function linkSegmentAnchor(
  link: IntersectionLink,
  center: [number, number],
): [number, number] {
  const path = link.path ?? []
  if (!path.length) return center

  let bestIdx = 0
  let bestD = Infinity
  for (let i = 0; i < path.length; i += 1) {
    const d = dist2(path[i], center)
    if (d < bestD) {
      bestD = d
      bestIdx = i
    }
  }

  const anchor: [number, number] = [path[bestIdx][0], path[bestIdx][1]]

  if (bestIdx + 1 < path.length) {
    const next = path[bestIdx + 1]
    if (dist2(next, center) > dist2(anchor, center)) {
      return [(anchor[0] + next[0]) / 2, (anchor[1] + next[1]) / 2]
    }
  }
  if (bestIdx > 0) {
    const prev = path[bestIdx - 1]
    if (dist2(prev, center) > dist2(anchor, center)) {
      return [(anchor[0] + prev[0]) / 2, (anchor[1] + prev[1]) / 2]
    }
  }
  return anchor
}

/** @deprecated use linkSegmentAnchor */
export const linkAnchor = linkSegmentAnchor

const METRIC_PHASES = new Set(['traffic', 'direction', 'saturation', 'imbalance'])

export function buildLinkCognitionMarkers(cognition: CognitionPayload | null): MapSceneMarker[] {
  if (!cognition?.intersection) return []
  const center: [number, number] = [cognition.intersection.lon, cognition.intersection.lat]
  const markers: MapSceneMarker[] = []

  for (const link of cognition.links ?? []) {
    if (!isEntrance(link.link_role) || !link.path?.length) continue
    const dir = normalizeDir(link.dir4_label || '')
    const [lon, lat] = linkSegmentAnchor(link, center)
    markers.push({
      id: `link-info-${link.link_id}`,
      lon,
      lat,
      kind: 'link-info',
      variant: 'link',
      title: `${dir}进口`,
      value: link.lane_num != null ? `${link.lane_num}车道` : '进口道',
      subtitle: link.road_name || link.link_id.slice(0, 10),
      severity: 'low',
      dir,
      link_id: link.link_id,
    })
  }
  return markers
}

const DIR4_TO_GROUP: Record<string, string> = {
  东: '东西向',
  西: '东西向',
  南: '南北向',
  北: '南北向',
  东南: '东南向',
  西南: '西南向',
  东北: '东北向',
  西北: '西北向',
}

function saturationForDir(
  dir: string,
  metrics: CognitionPayload['metrics_by_arm'],
  groups: CognitionPayload['direction_groups'],
): number | null {
  for (const metric of metrics ?? []) {
    if (normalizeDir(metric.dir4_label || '') !== dir) continue
    const sat = metric.saturation
    if (sat != null && Number(sat) > 0) return Number(sat)
  }
  const groupName = DIR4_TO_GROUP[dir]
  if (!groupName) return null
  for (const group of groups ?? []) {
    if (group.group !== groupName) continue
    const raw = group.saturation_max ?? group.saturation_avg
    if (raw != null && Number(raw) > 0) return Number(raw)
  }
  return null
}

export function buildArmMetricMarkers(cognition: CognitionPayload | null): MapSceneMarker[] {
  if (!cognition?.intersection) return []
  const center: [number, number] = [cognition.intersection.lon, cognition.intersection.lat]
  const links = cognition.links ?? []
  const metrics = cognition.metrics_by_arm ?? []
  const groups = cognition.direction_groups ?? []
  const markers: MapSceneMarker[] = []
  const seen = new Set<string>()

  for (const link of links) {
    if (!isEntrance(link.link_role) || !link.path?.length) continue
    const dir = normalizeDir(link.dir4_label || link.dir8_label || '')
    if (!dir || seen.has(dir)) continue
    seen.add(dir)
    const sat = saturationForDir(dir, metrics, groups)
    const [lon, lat] = linkSegmentAnchor(link, center)
    const severity =
      sat == null
        ? 'unknown'
        : sat >= 0.85
          ? 'high'
          : sat >= 0.65
            ? 'medium'
            : 'low'
    markers.push({
      id: `arm-metric-${link.link_id}`,
      lon,
      lat,
      kind: 'metric',
      variant: 'saturation',
      title: `${dir}进口`,
      value: sat != null ? sat.toFixed(2) : '—',
      subtitle: sat != null ? '饱和度' : '无数据',
      severity,
      dir,
      link_id: link.link_id,
    })
  }
  return markers
}

export function mergeSceneMarkers(
  action: MapActionEvent,
  cognition: CognitionPayload | null,
): MapSceneMarker[] {
  const sceneMarkers = action.markers ?? []
  if (sceneMarkers.length > 0) {
    return sceneMarkers
  }
  if (cognition && action.phase && METRIC_PHASES.has(action.phase)) {
    return buildArmMetricMarkers(cognition)
  }
  return sceneMarkers
}

const DIR_LINK_COLORS: Record<string, string> = {
  东: '#00e5ff',
  西: '#5ecbff',
  南: '#ffc266',
  北: '#9d7bff',
  东北: '#6dffb5',
  东南: '#ff8f8f',
  西北: '#c4f0ff',
  西南: '#ffb4b4',
}

export function linkStrokeColor(
  link: IntersectionLink,
  opts: {
    highlightDirs?: string[]
    protectedDirs?: string[]
    pulseIds?: string[]
    dimOthers?: boolean
    flashDirs?: string[]
    isProtected?: boolean
  },
): { color: string; weight: number; opacity: number; pulse: boolean; flash: boolean } {
  const dir = normalizeDir(link.dir4_label || '')
  const entrance = isEntrance(link.link_role)
  const isPulse = opts.pulseIds?.includes(link.link_id) ?? false
  const isHighlight = opts.highlightDirs?.some((d) => dir.includes(normalizeDir(d))) ?? false
  const isFlash = opts.flashDirs?.some((d) => dir.includes(normalizeDir(d))) ?? false
  const isProtected = opts.isProtected ?? false
  const dirColor = DIR_LINK_COLORS[dir] || TA_THEME.linkEntrance

  if (isProtected && !isFlash && !isPulse) {
    return {
      color: '#6dffb5',
      weight: entrance ? 8 : 5,
      opacity: 0.75,
      pulse: false,
      flash: false,
    }
  }

  if (isFlash || isPulse || isHighlight) {
    return {
      color: isFlash ? '#fff2a0' : TA_THEME.linkHighlight,
      weight: entrance ? 10 : 7,
      opacity: 0.98,
      pulse: true,
      flash: isFlash,
    }
  }
  if (opts.dimOthers) {
    return {
      color: entrance ? 'rgba(0,229,255,0.22)' : 'rgba(0,229,255,0.1)',
      weight: entrance ? 4 : 3,
      opacity: 0.35,
      pulse: false,
      flash: false,
    }
  }
  return {
    color: entrance ? dirColor : TA_THEME.linkExit,
    weight: entrance ? 7 : 4,
    opacity: entrance ? 0.95 : 0.5,
    pulse: false,
    flash: false,
  }
}

export function severityClass(sev?: string): string {
  if (sev === 'high') return 'sev-high'
  if (sev === 'medium') return 'sev-medium'
  if (sev === 'low') return 'sev-low'
  return 'sev-unknown'
}

export function markerHtml(m: {
  kind?: string
  variant?: string
  title?: string
  subtitle?: string
  value?: string
  severity?: string
  dir?: string
}): string {
  const sev = severityClass(m.severity)
  const kind = m.kind || 'chip'
  const variant = m.variant || kind
  const dirClass = m.dir ? `dir-${m.dir}` : ''

  if (kind === 'link-info' || variant === 'link') {
    return `<div class="map-marker link-info ${dirClass}">
      <div class="marker-badge">LINK</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (kind === 'evidence' || variant === 'evidence') {
    return `<div class="map-marker evidence ${sev} ${dirClass}">
      <div class="marker-badge">证据</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (variant === 'protected') {
    return `<div class="map-marker protected ${sev} ${dirClass}">
      <div class="marker-badge">保护</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (kind === 'suggestion' || variant === 'suggestion') {
    return `<div class="map-marker suggestion ${sev} ${dirClass}">
      <div class="marker-arrow">▲</div>
      <div class="marker-badge">建议</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
    </div>`
  }
  if (kind === 'rule' || variant === 'rule') {
    return `<div class="map-marker rule ${sev} ${dirClass}">
      <div class="marker-icon">◎</div>
      <div class="marker-badge">规则</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (kind === 'alert' || variant === 'alert') {
    return `<div class="map-marker alert ${sev} ${dirClass}">
      <div class="marker-pulse"></div>
      <div class="marker-badge">告警</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
    </div>`
  }
  if (variant === 'delay') {
    return `<div class="map-marker delay ${sev} ${dirClass}">
      <div class="marker-icon">⏱</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '延误')}</div>
    </div>`
  }
  if (kind === 'imbalance' || variant === 'imbalance') {
    return `<div class="map-marker imbalance ${sev} ${dirClass}">
      <div class="marker-badge">失衡</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
    </div>`
  }
  if (kind === 'metric' || variant === 'saturation') {
    return `<div class="map-marker metric saturation ${sev} ${dirClass}">
      <div class="marker-badge">饱和</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (variant === 'direction') {
    return `<div class="map-marker direction ${sev} ${dirClass}">
      <div class="marker-compass">🧭</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
    </div>`
  }
  if (kind === 'timing' || variant === 'deficit') {
    return `<div class="map-marker timing ${sev} ${dirClass}">
      <div class="marker-badge">配时</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  if (kind === 'corridor-scan' || variant === 'rank' || variant === 'no-data') {
    const rank = (m as { rank?: number | null }).rank
    const selected = (m as { selected?: boolean }).selected
    const rankLabel = rank != null ? String(rank) : '·'
    return `<div class="map-marker corridor-pin ${sev} ${variant === 'no-data' ? 'no-data' : ''} ${selected ? 'selected' : ''}">
      <span class="pin-rank">${escapeHtml(rankLabel)}</span>
      <span class="pin-value">${escapeHtml(m.value || '—')}</span>
    </div>`
  }
  if (kind === 'corridor' || variant === 'peer' || variant === 'current') {
    return `<div class="map-marker corridor ${variant === 'current' ? 'corridor-current' : ''} ${sev}">
      <div class="marker-badge">协调</div>
      <div class="marker-value">${escapeHtml(m.value || '')}</div>
      <div class="marker-title">${escapeHtml(m.title || '')}</div>
      <div class="marker-sub">${escapeHtml(m.subtitle || '')}</div>
    </div>`
  }
  return `<div class="map-marker chip ${sev} ${dirClass}">
    <div class="marker-value">${escapeHtml(m.value || '')}</div>
    <div class="marker-title">${escapeHtml(m.title || '')}</div>
  </div>`
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
