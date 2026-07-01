import { interpolatePath, particleDurationFor, type LngLat } from '../utils/traceParticles'
import { upstreamEdgeStrokeWeight } from '../utils/upstreamStoryboard'
import type { UpstreamCorrelateMap } from '../types/map'

type AMapNS = typeof AMap
type AMapMapInstance = InstanceType<typeof AMap.Map>
type Overlay = InstanceType<typeof AMap.Polyline> | InstanceType<typeof AMap.Marker>

interface Particle {
  marker: InstanceType<typeof AMap.Marker>
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

/**
 * 单链路流量溯源渲染层：发光干线（外层 glow + 亮核）、沿线流动粒子（rAF + setPosition）、
 * 节点脉冲、极简标签。所有覆盖物按 id 幂等注册，reset/dispose 释放并停止动画。
 */
export class UpstreamTraceLayer {
  private readonly AMap: AMapNS
  private readonly map: AMapMapInstance
  private readonly byId = new Map<string, Overlay[]>()
  private readonly fitList: Overlay[] = []
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

  /** 节点脉冲：目标=红、治理落点=绿、上游=琥珀（由 CSS class 决定）。 */
  revealNode(
    id: string,
    lon: number,
    lat: number,
    opts: { role?: string; dim?: boolean } = {},
  ): void {
    const key = `node:${id}`
    if (this.byId.has(key)) return
    const role = opts.role ?? 'upstream'
    const roleCls = role === 'target' ? 'is-target' : role === 'governance' ? 'is-gov' : ''
    const marker = new this.AMap.Marker({
      position: [lon, lat],
      anchor: 'center',
      zIndex: 95,
      content: `<div class="us-node ${roleCls}${opts.dim ? ' is-dim' : ''}"></div>`,
    })
    this.register(key, marker)
  }

  /** 极简标签：跳数 + 路口名 + 饱和/流量。html 由调用方拼装。 */
  revealLabel(
    id: string,
    lon: number,
    lat: number,
    html: string,
    offset: [number, number],
  ): void {
    const key = `label:${id}`
    if (this.byId.has(key)) return
    const marker = new this.AMap.Marker({
      position: [lon, lat],
      anchor: 'center',
      offset: new this.AMap.Pixel(offset[0], offset[1]),
      zIndex: 96,
      content: html,
    })
    this.register(key, marker)
  }

  /** 溯源表全量路口：按路口绘制全部 link + 节点 + 标签。 */
  renderCorrelateMap(data: UpstreamCorrelateMap): void {
    const COLORS = {
      target: '#22c55e',
      main: '#f59e0b',
      other: '#3b82f6',
      exit: '#475569',
    }
    for (const node of data.intersections) {
      const isTarget = node.role === 'target'
      const isMain = Boolean(node.in_main_corridor)
      const baseColor = isTarget ? COLORS.target : isMain ? COLORS.main : COLORS.other
      const nodeId = node.inter_id

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
      })

      if (isTarget) continue
      const cov = node.path_coverage
      if (cov == null || cov < 8) continue
      const hopTxt = isMain && node.corridor_hop ? `走廊#${node.corridor_hop}` : '其他向'
      const html =
        `<div class="us-label">` +
        `<div class="us-hop">${hopTxt}</div>` +
        `<div class="us-name">${node.name}</div>` +
        `<div class="us-metric" style="color:#fbbf24">途经 ${cov.toFixed(1)}%</div>` +
        `</div>`
      this.revealLabel(nodeId, lon, lat, html, [10, -48])
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
