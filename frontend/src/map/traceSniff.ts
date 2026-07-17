import { validPath } from '@/utils/guards'
import type { LngLat } from './traceParticles'
import { MIN_PATH_COVERAGE } from './traceLabels'

export type SniffTraceDirection = 'upstream' | 'downstream'
export type SniffNodeRole = 'target' | 'upstream' | 'downstream'

export interface TraceSniffLink {
  link_id?: string | null
  link_role?: string | null
  dir4_label?: string | null
  dir8_code?: number | string | null
  dir8_label?: string | null
  lane_num?: number | string | null
  road_name?: string | null
  path?: LngLat[]
}

export interface TraceSniffIntersection {
  inter_id?: string | null
  name?: string | null
  center?: LngLat | null
  role?: SniffNodeRole | string | null
  path_coverage?: number | null
  in_main_corridor?: boolean | null
  corridor_hop?: number | null
  is_topo_anchor?: boolean | null
  links?: TraceSniffLink[]
}

export interface TraceSniffScene {
  available?: boolean
  trace_direction?: SniffTraceDirection | string | null
  intersections?: TraceSniffIntersection[]
  stats?: Record<string, unknown>
  visualization?: TraceSpreadVisualization
}

export interface TraceSpreadVisualization {
  contract_version?: string
  effect?: string
  direction?: string
  origin?: LngLat | null
  geometry_source?: string
  context_geometry_source?: string | null
  render_geometry_scope?: string
  ordering?: string
  particle_anchor?: string
  particle_color?: string
  particle_texture?: string | null
  particle_count?: number
  particle_color_mode?: string
  propagation_renderer?: string
  repeat?: boolean
  color_metric?: string
  color_semantics?: string
  camera?: { pitch?: number; radius_m?: number; max_zoom?: number }
  palette?: {
    trace?: string
    severe?: string
    high?: string
    medium?: string
    low?: string
    near?: string
    middle?: string
    far?: string
  }
  map_style?: string
  road_classification_source?: string | null
  source?: string
}

export interface TraceSniffSummary {
  targetLinks: number
  mainLinks: number
  otherLinks: number
  visibleNodes: number
}

export interface LegacySniffInput {
  target?: {
    inter_id?: string | null
    inter_name?: string | null
    intersection_name?: string | null
    lng?: number | null
    lat?: number | null
  } | null
  channelizationMap?: { links?: TraceSniffLink[] } | null
  upstreamTraces?: Array<{
    upstream_inter_id?: string | null
    upstream_inter_name?: string | null
    upstream_lng?: number | null
    upstream_lat?: number | null
    path?: LngLat[]
    dominant_movement?: { share_pct?: number | null } | null
    upstream_movements?: Array<{ share_pct?: number | null }>
  }>
  downstreamTraces?: Array<{
    downstream_inter_id?: string | null
    name?: string | null
    lon?: number | null
    lat?: number | null
    share_pct?: number | null
    path?: LngLat[]
  }>
}

export function isEntranceLink(role?: string | null): boolean {
  const raw = String(role ?? '').toLowerCase()
  return raw === 'entrance' || raw === '进口'
}

export function sniffCoverage(node: TraceSniffIntersection): number | null {
  const value = Number(node.path_coverage)
  return Number.isFinite(value) ? value : null
}

export function shouldRenderSniffNode(node: TraceSniffIntersection): boolean {
  if (node.role === 'target') return true
  const coverage = sniffCoverage(node)
  if (coverage == null) return Boolean(node.in_main_corridor || node.is_topo_anchor)
  return coverage >= MIN_PATH_COVERAGE
}

export function sniffNodeId(node: TraceSniffIntersection, index: number): string {
  return String(node.inter_id || node.name || `sniff-${index}`)
}

export function sniffLinkPath(link: TraceSniffLink): LngLat[] {
  return validPath(link.path)
}

export function summarizeSniffScene(scene: TraceSniffScene | null | undefined): TraceSniffSummary {
  const summary: TraceSniffSummary = {
    targetLinks: 0,
    mainLinks: 0,
    otherLinks: 0,
    visibleNodes: 0,
  }
  for (const node of scene?.intersections ?? []) {
    if (!shouldRenderSniffNode(node)) continue
    const links = (node.links ?? []).filter((link) => sniffLinkPath(link).length >= 2)
    if (!links.length && !node.center) continue
    summary.visibleNodes += 1
    if (node.role === 'target') summary.targetLinks += links.length
    else if (node.in_main_corridor) summary.mainLinks += links.length
    else summary.otherLinks += links.length
  }
  return summary
}

function numberOrNull(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function centerFrom(lng: unknown, lat: unknown): LngLat | null {
  const x = numberOrNull(lng)
  const y = numberOrNull(lat)
  return x == null || y == null ? null : [x, y]
}

export function buildLegacySniffScene(input: LegacySniffInput): TraceSniffScene {
  const intersections: TraceSniffIntersection[] = []
  const targetCenter = centerFrom(input.target?.lng, input.target?.lat)
  const targetLinks = (input.channelizationMap?.links ?? []).filter((link) => sniffLinkPath(link).length >= 2)
  if (targetCenter || targetLinks.length) {
    intersections.push({
      inter_id: input.target?.inter_id,
      name: input.target?.inter_name ?? input.target?.intersection_name ?? '目标路口',
      center: targetCenter,
      role: 'target',
      in_main_corridor: false,
      links: targetLinks,
    })
  }

  const upstream = input.upstreamTraces ?? []
  upstream.forEach((trace, index) => {
    const path = validPath(trace.path)
    const center = centerFrom(trace.upstream_lng, trace.upstream_lat) ?? path[0] ?? null
    if (!center || path.length < 2) return
    const coverage = trace.dominant_movement?.share_pct ?? trace.upstream_movements?.[0]?.share_pct ?? null
    intersections.push({
      inter_id: trace.upstream_inter_id ?? `legacy-up-${index}`,
      name: trace.upstream_inter_name ?? '上游路口',
      center,
      role: 'upstream',
      path_coverage: coverage,
      in_main_corridor: index === 0 || coverage != null,
      corridor_hop: index + 1,
      is_topo_anchor: index === 0,
      links: [{ link_id: `legacy-up-${index}`, link_role: 'entrance', path }],
    })
  })

  if (intersections.length <= 1) {
    ;(input.downstreamTraces ?? []).forEach((trace, index) => {
      const path = validPath(trace.path)
      const center = centerFrom(trace.lon, trace.lat) ?? path[path.length - 1] ?? null
      if (!center || path.length < 2) return
      intersections.push({
        inter_id: trace.downstream_inter_id ?? `legacy-down-${index}`,
        name: trace.name ?? '下游路口',
        center,
        role: 'downstream',
        path_coverage: trace.share_pct ?? null,
        in_main_corridor: index === 0 || trace.share_pct != null,
        corridor_hop: index + 1,
        is_topo_anchor: index === 0,
        links: [{ link_id: `legacy-down-${index}`, link_role: 'exit', path }],
      })
    })
  }

  return {
    available: intersections.some((node) => (node.links ?? []).some((link) => sniffLinkPath(link).length >= 2)),
    trace_direction: upstream.length ? 'upstream' : 'downstream',
    intersections,
  }
}
