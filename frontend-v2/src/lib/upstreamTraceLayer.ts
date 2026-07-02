import { interpolatePath, particleDurationFor, type LngLat } from '../utils/traceParticles'
import { upstreamEdgeStrokeWeight } from '../utils/upstreamStoryboard'
import {
  buildCorrelateLabelHtml,
  coverageNodeStyle,
  defaultOpenUpstreamId,
  isRenderableUpstream,
} from '../utils/upstreamCorrelateLabels'
import type { CorrelateTraceIntersection, UpstreamCorrelateMap } from '../types/map'

type AMapNS = typeof AMap
type AMapMapInstance = InstanceType<typeof AMap.Map>
type AMapMarker = InstanceType<typeof AMap.Marker>
type Overlay = InstanceType<typeof AMap.Polyline> | AMapMarker

interface Particle {
  marker: AMapMarker
  path: LngLat[]
  offset: number
  duration: number
}

/** 干线发光配色（对齐参考项目「干线诊断」琥珀暖色 + 深底标签）。 */
const TRACE_COLORS = {
  glow: '#f5a623',
  core: '#ffcf7a',
} as const

const PARTICLES_PER_EDGE = 3
const LABEL_OFFSET: [number, number] = [10, -48]

/**
 * 单链路流量溯源渲染层：发光干线（外层 glow + 亮核）、沿线流动粒子（rAF + setPosition）、
 * 节点脉冲、极简标签。所有覆盖物按 id 幂等注册，reset/dispose 释放并停止动画。
 */
export class UpstreamTraceLayer {
  private readonly AMap: AMapNS
  private readonly map: AMapMapInstance
  private readonly byId = new Map<string, Overlay[]>()
  private readonly fitList: Overlay[] = []
  private readonly labelMarkers = new Map<string, AMapMarker>()
  private readonly openLabelIds = new Set<string>()
  private particles: Particle[] = []
  private rafId: number | null = null

  constructor(amap: AMapNS, map: AMapMapInstance) {
    this.AMap = amap
    this.map = map
  }

  hasOverlay(id: string): boolean {
    return this.byId.has(id)
  }

  private register(id: string, overlay: Overlay): void {
    overlay.setMap(this.map)
    const list = this.byId.get(id) ?? []
    list.push(overlay)
    this.byId.set(id, list)
    this.fitList.push(overlay)
  }

  /** 发光干线：外层低透 glow + 亮核线，末段带方向箭头，并沿线投放流动粒子。 */
  revealEdge(
    id: string,
    path: LngLat[],
    opts: { dim?: boolean; flowPct?: number | null } = {},
  ): void {
    if (this.byId.has(id) || path.length < 2) return
    const dim = Boolean(opts.dim)
    const weight = upstreamEdgeStrokeWeight(opts.flowPct)

    const glow = new this.AMap.Polyline({
      path,
      strokeColor: TRACE_COLORS.glow,
      strokeWeight: weight * 3,
      strokeOpacity: dim ? 0.06 : 0.2,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: 68,
    })
    const core = new this.AMap.Polyline({
      path,
      strokeColor: TRACE_COLORS.core,
      strokeWeight: weight,
      strokeOpacity: dim ? 0.3 : 0.95,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: true,
      zIndex: 72,
    })
    this.register(id, glow)
    this.register(id, core)

    if (!dim) this.addParticles(id, path)
  }

  /** 上游路口十字来流段：线宽/透明度随 share_pct 变化。 */
  revealFeedSegment(
    id: string,
    path: LngLat[],
    opts: { sharePct?: number | null; dim?: boolean } = {},
  ): void {
    if (this.byId.has(id) || path.length < 2) return
    const dim = Boolean(opts.dim)
    const pct = Math.max(0, Math.min(100, Number(opts.sharePct) || 0))
    const weight = 2.2 + Math.sqrt(pct / 100) * 4.5
    const opacity = dim ? 0.25 : 0.35 + (pct / 100) * 0.55

    const glow = new this.AMap.Polyline({
      path,
      strokeColor: TRACE_COLORS.glow,
      strokeWeight: weight * 2.2,
      strokeOpacity: opacity * 0.35,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: 74,
    })
    const core = new this.AMap.Polyline({
      path,
      strokeColor: TRACE_COLORS.core,
      strokeWeight: weight,
      strokeOpacity: opacity,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: true,
      zIndex: 78,
    })
    this.register(id, glow)
    this.register(id, core)
  }

  private addParticles(edgeId: string, path: LngLat[]): void {
    const duration = particleDurationFor(path)
    for (let i = 0; i < PARTICLES_PER_EDGE; i++) {
      const marker = new this.AMap.Marker({
        position: path[0],
        anchor: 'center',
        zIndex: 90,
        content: '<div class="us-particle"></div>',
      })
      this.register(`${edgeId}:p${i}`, marker)
      this.particles.push({
        marker,
        path,
        offset: i / PARTICLES_PER_EDGE,
        duration,
      })
    }
    this.startRaf()
  }

  private startRaf(): void {
    if (this.rafId != null || typeof requestAnimationFrame !== 'function') return
    const tick = (now: number) => {
      for (const p of this.particles) {
        const t = (now / p.duration + p.offset) % 1
        const pos = interpolatePath(p.path, t)
        if (pos) p.marker.setPosition(pos)
      }
      this.rafId = requestAnimationFrame(tick)
    }
    this.rafId = requestAnimationFrame(tick)
  }

  private upstreamNodeContent(
    role: string,
    opts: { dim?: boolean; coverage?: number | null },
  ): string {
    const roleCls =
      role === 'target' ? 'is-target' : role === 'governance' ? 'is-gov' : ''
    const dimCls = opts.dim ? ' is-dim' : ''
    if (role !== 'upstream' || opts.coverage == null) {
      return `<div class="us-node ${roleCls}${dimCls}"></div>`
    }
    const { size, opacity, glow } = coverageNodeStyle(opts.coverage)
    const shadow = (14 * glow).toFixed(1)
    const shadowOuter = (34 * glow).toFixed(1)
    const alpha = (0.78 * glow).toFixed(2)
    const alphaOuter = (0.26 * glow).toFixed(2)
    return (
      `<div class="us-node is-scaled ${roleCls}${dimCls}" ` +
      `style="width:${size}px;height:${size}px;opacity:${opacity.toFixed(2)};` +
      `box-shadow:0 0 ${shadow}px rgba(245,166,35,${alpha}),0 0 ${shadowOuter}px rgba(245,166,35,${alphaOuter})">` +
      `</div>`
    )
  }

  /** 节点脉冲：目标=红、治理落点=绿、上游=琥珀（由 CSS class 决定）。 */
  revealNode(
    id: string,
    lon: number,
    lat: number,
    opts: {
      role?: string
      dim?: boolean
      coverage?: number | null
      clickable?: boolean
      onClick?: () => void
    } = {},
  ): void {
    const key = `node:${id}`
    if (this.byId.has(key)) return
    const role = opts.role ?? 'upstream'
    const clickable = Boolean(opts.clickable)
    const marker = new this.AMap.Marker({
      position: [lon, lat],
      anchor: 'center',
      zIndex: 95,
      content: this.upstreamNodeContent(role, opts),
      cursor: clickable ? 'pointer' : undefined,
    })
    if (clickable && opts.onClick) {
      marker.on('click', opts.onClick)
    }
    this.register(key, marker)
  }

  private setLabelVisible(nodeId: string, visible: boolean): void {
    const marker = this.labelMarkers.get(nodeId)
    if (!marker) return
    marker.setMap(visible ? this.map : null)
    if (visible) this.openLabelIds.add(nodeId)
    else this.openLabelIds.delete(nodeId)
  }

  private toggleLabel(nodeId: string): void {
    this.setLabelVisible(nodeId, !this.openLabelIds.has(nodeId))
  }

  private ensureLabel(node: CorrelateTraceIntersection): void {
    const nodeId = node.inter_id
    if (this.labelMarkers.has(nodeId)) return
    const [lon, lat] = node.center
    const marker = new this.AMap.Marker({
      position: [lon, lat],
      anchor: 'center',
      offset: new this.AMap.Pixel(LABEL_OFFSET[0], LABEL_OFFSET[1]),
      zIndex: 96,
      content: buildCorrelateLabelHtml(node),
    })
    marker.setMap(null)
    this.labelMarkers.set(nodeId, marker)
    const key = `label:${nodeId}`
    const list = this.byId.get(key) ?? []
    list.push(marker)
    this.byId.set(key, list)
    this.fitList.push(marker)
  }

  private labelEligible(node: CorrelateTraceIntersection): boolean {
    return node.role === 'upstream' && isRenderableUpstream(node)
  }

  /** 溯源表路口：仅渲染有效上游（≥5% 途经、有 link/坐标）+ 目标路口。 */
  renderCorrelateMap(data: UpstreamCorrelateMap): void {
    const COLORS = {
      target: '#22c55e',
      main: '#f59e0b',
      other: '#3b82f6',
      exit: '#475569',
    }
    const defaultOpenId = defaultOpenUpstreamId(data)

    for (const node of data.intersections) {
      if (!isRenderableUpstream(node)) continue
      const isTarget = node.role === 'target'
      const isMain = Boolean(node.in_main_corridor)
      const baseColor = isTarget ? COLORS.target : isMain ? COLORS.main : COLORS.other
      const nodeId = node.inter_id
      const canLabel = this.labelEligible(node)

      for (const link of node.links) {
        const ent = link.link_role === 'entrance' || link.link_role === '进口'
        const path = (link.path ?? []) as LngLat[]
        if (path.length < 2) continue
        const lid = `link:${nodeId}:${link.link_id}`
        const pl = new this.AMap.Polyline({
          path,
          strokeColor: ent ? baseColor : COLORS.exit,
          strokeOpacity: ent ? (isTarget ? 0.7 : 0.5) : 0.25,
          strokeWeight: ent ? Math.max(3, Math.min(8, 2 + (link.lane_num ?? 0) * 0.5)) : 2,
          zIndex: isTarget ? 60 : isMain ? 45 : 25,
          lineJoin: 'round',
          lineCap: 'round',
        })
        this.register(lid, pl)
      }

      const [lon, lat] = node.center
      this.revealNode(nodeId, lon, lat, {
        role: isTarget ? 'target' : 'upstream',
        coverage: isTarget ? null : node.path_coverage,
        clickable: canLabel,
        onClick: canLabel ? () => this.toggleLabel(nodeId) : undefined,
      })

      if (!canLabel) continue
      this.ensureLabel(node)
      if (nodeId === defaultOpenId) {
        this.setLabelVisible(nodeId, true)
      }
    }
  }

  /** 供 setFitView 收束整链。 */
  overlays(): Overlay[] {
    return this.fitList.filter(Boolean)
  }

  reset(): void {
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
    this.particles = []
    this.labelMarkers.clear()
    this.openLabelIds.clear()
    for (const list of this.byId.values()) {
      for (const overlay of list) (overlay as { setMap: (m: null) => void }).setMap(null)
    }
    this.byId.clear()
    this.fitList.length = 0
  }

  dispose(): void {
    this.reset()
  }
}

export function createUpstreamTraceLayer(
  amap: AMapNS,
  map: AMapMapInstance,
): UpstreamTraceLayer {
  return new UpstreamTraceLayer(amap, map)
}
