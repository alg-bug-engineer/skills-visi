import { validPath } from '@/utils/guards'
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
  metrics?: DownstreamTopologyMetrics
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

export interface DownstreamTopology {
  target: LngLat | null
  nodes: DownstreamTopologyNode[]
  edges: DownstreamTopologyEdge[]
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

export function buildDownstreamTopology(mapScenes: Record<string, any> | undefined, target: LngLat | null): DownstreamTopology {
  const channel = mapScenes?.channelization_map
  const downstream = mapScenes?.downstream_trace_map
  const highlighted = new Set<string>((downstream?.turn_traces ?? []).map(nodeIdFromTrace).filter(Boolean))
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
    const isHighlighted = highlighted.has(id)
    nodes.set(id, {
      id,
      name: String(link.adjacent_inter_name ?? link.dir8_label ?? '下游路口'),
      position,
      linkId: link.link_id,
      highlighted: isHighlighted,
      metrics: mergeMetrics(adjacentMetrics.get(id), metricFromRecord(link)),
    })
    edges.push({ id: String(link.link_id ?? id), path, highlighted: isHighlighted })
  }

  for (const trace of downstream?.turn_traces ?? []) {
    const path = validPath(trace.path)
    if (path.length < 2) continue
    const id = nodeIdFromTrace(trace)
    if (!id || nodes.has(id)) continue
    const lng = Number(trace.lon)
    const lat = Number(trace.lat)
    nodes.set(id, {
      id,
      name: String(trace.name ?? '下游路口'),
      position: Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : path[path.length - 1],
      highlighted: true,
      metrics: mergeMetrics(adjacentMetrics.get(id), metricFromRecord(trace)),
    })
    edges.push({ id: `trace:${id}`, path, highlighted: true })
  }

  return { target, nodes: [...nodes.values()], edges }
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
      this.add(
        new this.amap.Marker({
          position: node.position,
          anchor: 'center',
          zIndex: node.highlighted ? 91 : 88,
          content: `<div class="topology-wrap ${node.highlighted ? 'is-hot' : ''}"><div class="topology-node"></div><div class="topology-label"><strong>${node.name}</strong><span>${formatNodeMetrics(node.metrics)}</span></div></div>`,
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

function fmtPct(v: number | null | undefined): string {
  return v == null ? '暂无' : `${Math.round(v * 100)}%`
}

export function formatNodeMetrics(metrics: DownstreamTopologyMetrics | undefined): string {
  if (!metrics) return '指标暂无'
  const parts: string[] = []
  if (metrics.queueRatio != null) {
    parts.push(`排队 ${fmtPct(metrics.queueRatio)}`)
  }
  if (metrics.saturation != null && metrics.saturation > 0) {
    parts.push(`饱和 ${fmtPct(metrics.saturation)}`)
  }
  if (metrics.greenUtilization != null) {
    parts.push(`绿灯 ${fmtPct(metrics.greenUtilization)}`)
  }
  return parts.length ? parts.join(' · ') : '指标暂无'
}
