import { validPath } from '@/utils/guards'
import { ratio } from '@/utils/format'
import type { LngLat } from './channelizationGeometry'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any
type Overlay = any

export interface DownstreamTopologyNode {
  id: string
  name: string
  position: LngLat
  linkId?: string
  highlighted: boolean
  /** 承接判别镜头聚焦的主要下游。 */
  primary?: boolean
  metrics?: DownstreamTopologyMetrics
  movements?: DownstreamTopologyMovement[]
}

export interface DownstreamTopologyEdge {
  id: string
  path: LngLat[]
  highlighted: boolean
}

export interface DownstreamTopologyMetrics {
  queueRatio?: number | null
  saturation?: number | null
  greenUtilization?: number | null
  remainingStorageM?: number | null
}

export interface DownstreamTopologyMovement {
  turnLabel: string
  sharePct?: number | null
  selected: boolean
  blocked: boolean
}

export interface DownstreamTopology {
  target: LngLat | null
  nodes: DownstreamTopologyNode[]
  edges: DownstreamTopologyEdge[]
  primaryId?: string | null
}

export interface PrimaryDownstreamFocus {
  id: string
  name: string
  position: LngLat
}

/** 从诊断结果解析主要下游锚点（承接判别镜头聚焦用）。 */
export function resolvePrimaryDownstreamFocus(resp: {
  phases?: {
    diagnosis?: {
      downstream_diagnosis?: { primary_downstream?: { inter_id?: string | null; inter_name?: string | null } | null }
      map_scenes?: Record<string, any>
    } | null
  } | null
} | null): PrimaryDownstreamFocus | null {
  const diagnosis = resp?.phases?.diagnosis
  const primary = diagnosis?.downstream_diagnosis?.primary_downstream
  const scenes = (diagnosis?.map_scenes ?? {}) as Record<string, any>
  const compare = scenes.diagnosis_compare?.downstream
  const id = String(primary?.inter_id ?? compare?.inter_id ?? '').trim()
  const name = String(primary?.inter_name ?? compare?.inter_name ?? '主要下游')

  const candidates: Array<{ id?: string; name?: string; lng?: unknown; lat?: unknown; lon?: unknown }> = []
  if (compare) candidates.push(compare)
  for (const item of scenes.downstream_trace_map?.adjacent_intersections ?? []) candidates.push(item)
  for (const item of scenes.downstream_trace_map?.turn_traces ?? []) {
    candidates.push({
      id: item.downstream_inter_id ?? item.inter_id,
      name: item.downstream_inter_name ?? item.name,
      lng: item.lng ?? item.lon,
      lat: item.lat,
      lon: item.lon,
    })
  }
  for (const link of scenes.channelization_map?.links ?? []) {
    if (String(link.link_role ?? '').toLowerCase() !== 'exit') continue
    candidates.push({
      id: link.adjacent_inter_id,
      name: link.adjacent_inter_name,
      lng: link.adjacent_lng,
      lat: link.adjacent_lat,
    })
  }

  for (const item of candidates) {
    const itemId = String(item.id ?? '').trim()
    if (id && itemId && itemId !== id) continue
    const lng = Number(item.lng ?? item.lon)
    const lat = Number(item.lat)
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    if (id && itemId && itemId !== id) continue
    return {
      id: id || itemId || 'primary-downstream',
      name: String(item.name ?? name),
      position: [lng, lat],
    }
  }

  // 有 id 但坐标只在 compare 外匹配失败时，仍尝试任意同名节点
  if (!id) {
    for (const item of candidates) {
      const lng = Number(item.lng ?? item.lon)
      const lat = Number(item.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
      return {
        id: String(item.id ?? 'primary-downstream'),
        name: String(item.name ?? name),
        position: [lng, lat],
      }
    }
  }
  return null
}

function nodeIdFromTrace(trace: Record<string, unknown>): string {
  return String(trace.downstream_inter_id ?? trace.inter_id ?? trace.name ?? '')
}

function num(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function metricFromRecord(record: Record<string, any> | undefined): DownstreamTopologyMetrics | undefined {
  if (!record) return undefined
  const metrics = record.metrics ?? record
  const result: DownstreamTopologyMetrics = {
    queueRatio: num(metrics.queue_storage_ratio_max ?? metrics.queue_ratio),
    saturation: num(metrics.saturation_rate ?? metrics.saturation),
    greenUtilization: num(metrics.green_utilization),
    remainingStorageM: num(record.remaining_storage_m ?? metrics.remaining_storage_m),
  }
  return Object.values(result).some((v) => v != null) ? result : undefined
}

function mergeMetrics(
  primary: DownstreamTopologyMetrics | undefined,
  fallback: DownstreamTopologyMetrics | undefined,
): DownstreamTopologyMetrics | undefined {
  const merged = {
    queueRatio: primary?.queueRatio ?? fallback?.queueRatio ?? undefined,
    saturation: primary?.saturation ?? fallback?.saturation ?? undefined,
    greenUtilization: primary?.greenUtilization ?? fallback?.greenUtilization ?? undefined,
    remainingStorageM: primary?.remainingStorageM ?? fallback?.remainingStorageM ?? undefined,
  }
  return Object.values(merged).some((v) => v != null) ? merged : undefined
}

export function buildDownstreamTopology(
  mapScenes: Record<string, any> | undefined,
  target: LngLat | null,
  opts: { primaryId?: string | null; primaryFocus?: PrimaryDownstreamFocus | null } = {},
): DownstreamTopology {
  const channel = mapScenes?.channelization_map
  const downstream = mapScenes?.downstream_trace_map
  const primaryId = String(opts.primaryId ?? opts.primaryFocus?.id ?? '').trim()
  const highlighted = new Set<string>((downstream?.turn_traces ?? []).map(nodeIdFromTrace).filter(Boolean))
  if (primaryId) highlighted.add(primaryId)
  const movementsByNode = new Map<string, DownstreamTopologyMovement[]>()
  for (const trace of downstream?.turn_traces ?? []) {
    const id = nodeIdFromTrace(trace)
    if (!id) continue
    const turnLabel = String(trace.turn_label ?? trace.movement ?? '').replace(/^.*进口/, '') || '转向'
    movementsByNode.set(id, [
      ...(movementsByNode.get(id) ?? []),
      {
        turnLabel,
        sharePct: num(trace.share_pct),
        selected: Boolean(trace.selected),
        blocked: Boolean(trace.capacity?.blocked),
      },
    ])
  }
  const adjacentMetrics = new Map<string, DownstreamTopologyMetrics>()
  for (const item of downstream?.adjacent_intersections ?? []) {
    const id = String(item.inter_id ?? item.adjacent_inter_id ?? '')
    const metrics = metricFromRecord(item)
    if (id && metrics) adjacentMetrics.set(id, metrics)
  }
  const nodes = new Map<string, DownstreamTopologyNode>()
  const edges: DownstreamTopologyEdge[] = []

  for (const link of channel?.links ?? []) {
    if (String(link.link_role ?? '').toLowerCase() !== 'exit') continue
    const path = validPath(link.path)
    if (path.length < 2) continue
    const id = String(link.adjacent_inter_id ?? link.link_id ?? '')
    if (!id) continue
    const lng = Number(link.adjacent_lng)
    const lat = Number(link.adjacent_lat)
    const position: LngLat = Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : path[path.length - 1]
    const isPrimary = Boolean(primaryId && id === primaryId)
    const isHighlighted = highlighted.has(id) || isPrimary
    nodes.set(id, {
      id,
      name: String(link.adjacent_inter_name ?? link.dir8_label ?? '下游路口'),
      position,
      linkId: link.link_id,
      highlighted: isHighlighted,
      primary: isPrimary,
      metrics: mergeMetrics(adjacentMetrics.get(id), metricFromRecord(link)),
      movements: movementsByNode.get(id),
    })
    edges.push({ id: String(link.link_id ?? id), path, highlighted: isHighlighted })
  }

  for (const trace of downstream?.turn_traces ?? []) {
    const path = validPath(trace.path)
    if (path.length < 2) continue
    const id = nodeIdFromTrace(trace)
    if (!id || nodes.has(id)) continue
    const lng = Number(trace.lon ?? trace.lng)
    const lat = Number(trace.lat)
    const isPrimary = Boolean(primaryId && id === primaryId)
    nodes.set(id, {
      id,
      name: String(trace.name ?? trace.downstream_inter_name ?? '下游路口'),
      position: Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : path[path.length - 1],
      highlighted: true,
      primary: isPrimary,
      metrics: mergeMetrics(adjacentMetrics.get(id), metricFromRecord(trace)),
      movements: movementsByNode.get(id),
    })
    edges.push({ id: `trace:${id}`, path, highlighted: true })
  }

  const focus = opts.primaryFocus
  if (focus && !nodes.has(focus.id)) {
    nodes.set(focus.id, {
      id: focus.id,
      name: focus.name,
      position: focus.position,
      highlighted: true,
      primary: true,
      metrics: adjacentMetrics.get(focus.id),
      movements: movementsByNode.get(focus.id),
    })
  } else if (focus && nodes.has(focus.id)) {
    const node = nodes.get(focus.id)!
    node.primary = true
    node.highlighted = true
    node.name = focus.name || node.name
  }

  return { target, nodes: [...nodes.values()], edges, primaryId: primaryId || null }
}

export class DownstreamTopologyLayer {
  private amap: AMapNS
  private map: AMapMap
  private overlays: Overlay[] = []

  constructor(amap: AMapNS, map: AMapMap) {
    this.amap = amap
    this.map = map
  }

  private add(overlay: Overlay) {
    this.overlays.push(overlay)
    this.map.add(overlay)
  }

  render(topology: DownstreamTopology) {
    if (topology.target) {
      this.add(
        new this.amap.Marker({
          position: topology.target,
          anchor: 'center',
          zIndex: 92,
          content: '<div class="topology-node is-target"></div>',
        }),
      )
    }

    for (const edge of topology.edges) {
      this.add(
        new this.amap.Polyline({
          path: edge.path,
          strokeColor: edge.highlighted ? '#38bdf8' : '#8aa0b8',
          strokeWeight: edge.highlighted ? 7 : 4,
          strokeOpacity: edge.highlighted ? 0.9 : 0.48,
          strokeStyle: edge.highlighted ? 'solid' : 'dashed',
          strokeDasharray: [10, 8],
          lineJoin: 'round',
          lineCap: 'round',
          showDir: true,
          zIndex: edge.highlighted ? 64 : 52,
        }),
      )
    }

    for (const node of topology.nodes) {
      const offsetClass = topologyLabelOffsetClass(topology.target, node.position)
      const hotClass = node.highlighted || node.primary ? 'is-hot' : ''
      const primaryClass = node.primary ? 'is-primary' : ''
      this.add(
        new this.amap.Marker({
          position: node.position,
          anchor: 'center',
          zIndex: node.primary ? 95 : node.highlighted ? 91 : 88,
          content:
            `<div class="topology-wrap ${hotClass} ${primaryClass} ${offsetClass}">` +
            (node.primary
              ? `<div class="downstream-pin" aria-hidden="true"><div class="downstream-pin__head"></div><div class="downstream-pin__stem"></div></div>`
              : `<div class="topology-node"></div>`) +
            `<div class="topology-label">` +
            (node.primary ? `<em class="topology-label__tag">主要下游</em>` : '') +
            `<strong>${node.name}</strong>` +
            `<span>${formatMovementSummary(node.movements)}</span>` +
            `<span>${formatNodeMetrics(node.metrics)}</span>` +
            `</div></div>`,
        }),
      )
    }
  }

  dispose() {
    if (this.overlays.length) {
      this.map.remove(this.overlays)
      this.overlays = []
    }
  }
}

export function formatNodeMetrics(metrics: DownstreamTopologyMetrics | undefined): string {
  if (!metrics) return '指标暂无'
  const parts: string[] = []
  if (metrics.queueRatio != null) {
    parts.push(`排队 ${ratio(metrics.queueRatio)}`)
  }
  if (metrics.saturation != null && metrics.saturation > 0) {
    parts.push(`饱和 ${ratio(metrics.saturation)}`)
  }
  if (metrics.greenUtilization != null) {
    parts.push(`绿灯 ${ratio(metrics.greenUtilization)}`)
  }
  return parts.length ? parts.join(' · ') : '指标暂无'
}

export function formatMovementSummary(movements: DownstreamTopologyMovement[] | undefined): string {
  if (!movements?.length) return '转向关系暂无'
  return movements
    .map((movement) => {
      const share = movement.sharePct == null ? '占比暂无' : `${Math.round(movement.sharePct)}%`
      const selected = movement.selected ? '（目标）' : ''
      const blocked = movement.blocked ? '·饱和' : ''
      return `${movement.turnLabel} ${share}${selected}${blocked}`
    })
    .join(' · ')
}

/** 相对目标路口方位，把卡片推到连线外侧，减少与箭头叠压。 */
export function topologyLabelOffsetClass(target: LngLat | null, position: LngLat): string {
  if (!target) return 'is-offset-s'
  const dLng = position[0] - target[0]
  const dLat = position[1] - target[1]
  if (Math.abs(dLng) >= Math.abs(dLat)) {
    return dLng >= 0 ? 'is-offset-e' : 'is-offset-w'
  }
  return dLat >= 0 ? 'is-offset-n' : 'is-offset-s'
}
