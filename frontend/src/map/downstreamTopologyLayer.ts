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
}

export interface DownstreamTopologyEdge {
  id: string
  path: LngLat[]
  highlighted: boolean
}

export interface DownstreamTopology {
  target: LngLat | null
  nodes: DownstreamTopologyNode[]
  edges: DownstreamTopologyEdge[]
}

function nodeIdFromTrace(trace: Record<string, unknown>): string {
  return String(trace.downstream_inter_id ?? trace.inter_id ?? trace.name ?? '')
}

export function buildDownstreamTopology(mapScenes: Record<string, any> | undefined, target: LngLat | null): DownstreamTopology {
  const channel = mapScenes?.channelization_map
  const downstream = mapScenes?.downstream_trace_map
  const highlighted = new Set<string>((downstream?.turn_traces ?? []).map(nodeIdFromTrace).filter(Boolean))
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
          content: `<div class="topology-wrap ${node.highlighted ? 'is-hot' : ''}"><div class="topology-node"></div><div class="topology-label">${node.name}</div></div>`,
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
