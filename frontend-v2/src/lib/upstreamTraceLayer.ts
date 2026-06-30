import { interpolatePath, particleDurationFor, type LngLat } from '../utils/traceParticles'
import { upstreamEdgeStrokeWeight } from '../utils/upstreamStoryboard'

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
