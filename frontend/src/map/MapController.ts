import type { ActMapScene } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import { hasCoord, validPath } from '@/utils/guards'
import { buildMetricMarkers, markerHtml } from './mapMarkers'
import { clampZoomUp, drillToIntersection, flyTo, panToVisualCenter } from './amapUtils'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any

const JINAN_CENTER: [number, number] = [117.02, 36.66]

/**
 * 地图控制器（纯 TS，包裹 AMap.Map 实例）。
 * 镜头连贯推进；覆盖物在镜头到位后绘制，避免闪现。
 */
export class MapController {
  private AMap: AMapNS
  private map: AMapMap
  private overlays: any[] = []
  private rafId: number | null = null
  private particles: Array<{ marker: any; path: [number, number][]; t: number; speed: number }> = []
  private currentZoom = 11
  private sceneToken = 0

  constructor(AMap: AMapNS, map: AMapMap) {
    this.AMap = AMap
    this.map = map
    this.currentZoom = map.getZoom?.() ?? 11
  }

  destroy() {
    this.clear()
    if (this.rafId != null) cancelAnimationFrame(this.rafId)
  }

  clear() {
    if (this.overlays.length) {
      this.map.remove(this.overlays)
      this.overlays = []
    }
    this.particles = []
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
  }

  private add(o: any) {
    this.overlays.push(o)
    this.map.add(o)
  }

  /** 应用某一幕：连贯镜头 + 该幕覆盖物。 */
  async applyScene(scene: ActMapScene, resp: RunResponse | null, showMetrics = false) {
    const token = ++this.sceneToken
    this.clear()

    const ticket = resp?.diagnosis_ticket
    const target: [number, number] | null =
      ticket && hasCoord(ticket.lng, ticket.lat) ? [ticket.lng as number, ticket.lat as number] : null

    const targetZoom = clampZoomUp(this.currentZoom, scene.zoom ?? this.currentZoom)

    try {
      this.map.setPitch?.(scene.pitch ?? 0)
    } catch {
      /* ignore */
    }

    switch (scene.kind) {
      case 'city':
        await flyTo(this.map, target ?? JINAN_CENTER, scene.zoom ?? 11, 900)
        this.currentZoom = scene.zoom ?? 11
        break
      case 'intersection':
        if (target) {
          await drillToIntersection(this.map, target, targetZoom)
          this.currentZoom = targetZoom
        }
        break
      case 'lane':
        if (target) {
          await drillToIntersection(this.map, target, targetZoom)
          this.currentZoom = targetZoom
        }
        break
      case 'trace':
      case 'corridor':
      case 'control':
        if (target) {
          const z = clampZoomUp(this.currentZoom, scene.zoom ?? 15)
          await flyTo(this.map, target, z, 800)
          panToVisualCenter(this.map, target)
          this.currentZoom = z
        }
        break
    }

    if (token !== this.sceneToken) return

    switch (scene.kind) {
      case 'intersection':
        if (target) this.drawIntersection(target, resp, false)
        break
      case 'lane':
        if (target) this.drawIntersection(target, resp, true)
        break
      case 'trace':
        this.drawTrace(resp, target)
        break
      case 'control':
        this.drawControlScope(resp, target)
        break
      case 'corridor':
        this.drawTrace(resp, target)
        break
    }

    if (showMetrics && target) this.drawMetricMarkers(resp, target)
  }

  private drawMetricMarkers(resp: RunResponse | null, center: [number, number]) {
    for (const spec of buildMetricMarkers(resp, center)) {
      this.add(
        new this.AMap.Marker({
          position: spec.position,
          content: markerHtml(spec),
          offset: new this.AMap.Pixel(-40, -28),
          anchor: 'center',
        }),
      )
    }
  }

  /** 路口虚线框 + 目标标记 + highlight_path。 */
  private drawIntersection(center: [number, number], resp: RunResponse | null, overflow = false) {
    const d = 0.0016
    const [lng, lat] = center
    const ring: [number, number][] = [
      [lng - d, lat - d],
      [lng + d, lat - d],
      [lng + d, lat + d],
      [lng - d, lat + d],
    ]
    this.add(
      new this.AMap.Polygon({
        path: ring,
        strokeColor: overflow ? '#ff5050' : '#00e5ff',
        strokeWeight: 2,
        strokeStyle: 'dashed',
        fillColor: overflow ? '#ff5050' : '#00e5ff',
        fillOpacity: overflow ? 0.08 : 0.04,
      }),
    )
    this.add(this.pulseMarker(center, overflow ? '#ff5050' : '#00e5ff', '目标路口'))

    const path = validPath(resp?.phases?.intent?.spatial_scene?.highlight_path)
    if (path.length >= 2) {
      this.add(
        new this.AMap.Polyline({
          path,
          strokeColor: '#00e5ff',
          strokeWeight: 6,
          strokeOpacity: 0.95,
          showDir: true,
        }),
      )
    }
    for (const n of resp?.phases?.intent?.spatial_scene?.upstream_nodes ?? []) {
      if (hasCoord(n.lng, n.lat))
        this.add(this.pulseMarker([n.lng as number, n.lat as number], '#f5a623', String(n.inter_name ?? '上游')))
    }
    for (const n of resp?.phases?.intent?.spatial_scene?.downstream_nodes ?? []) {
      if (hasCoord(n.lng, n.lat))
        this.add(this.pulseMarker([n.lng as number, n.lat as number], '#38bdf8', String(n.inter_name ?? '下游')))
    }
  }

  private drawTrace(resp: RunResponse | null, target: [number, number] | null) {
    if (target) this.add(this.pulseMarker(target, '#00e5ff', '目标路口'))
    const scenes = resp?.phases?.diagnosis?.map_scenes ?? {}
    const traces = [
      ...(scenes.downstream_trace_map?.turn_traces ?? []),
      ...(resp?.phases?.diagnosis?.flow_trace?.entry_traces ?? []),
    ]
    let drawn = 0
    for (const tr of traces) {
      const path = validPath(tr.path)
      if (path.length < 2) continue
      const upstream = tr.trace_kind === 'upstream'
      const glow = upstream ? '#f5a623' : '#0ea5e9'
      const core = upstream ? '#ffcf7a' : '#38bdf8'
      this.add(new this.AMap.Polyline({ path, strokeColor: glow, strokeWeight: 18, strokeOpacity: 0.2 }))
      this.add(new this.AMap.Polyline({ path, strokeColor: core, strokeWeight: 6, strokeOpacity: 0.95, showDir: true }))
      const marker = new this.AMap.Marker({
        position: path[0],
        content: `<div class="us-particle" style="background:${core}"></div>`,
        offset: new this.AMap.Pixel(-4, -4),
      })
      this.add(marker)
      this.particles.push({ marker, path, t: Math.random(), speed: 0.004 + Math.random() * 0.004 })
      drawn++
    }
    if (drawn > 0) this.startParticles()
  }

  private drawControlScope(resp: RunResponse | null, target: [number, number] | null) {
    const csm = resp?.phases?.strategy?.control_scope_map
    const center = csm?.center && hasCoord(csm.center[0], csm.center[1]) ? (csm.center as [number, number]) : target
    if (center) this.add(this.pulseMarker(center, '#00e5ff', '小步释放'))
    for (const p of csm?.upstream_metering_points ?? []) {
      const lng = (p as any).lng
      const lat = (p as any).lat
      if (hasCoord(lng, lat)) this.add(this.pulseMarker([lng, lat], '#ff5050', '控流闸口'))
    }
    for (const p of csm?.downstream_protection_nodes ?? []) {
      const lng = (p as any).lng
      const lat = (p as any).lat
      if (hasCoord(lng, lat)) this.add(this.pulseMarker([lng, lat], '#6dffb5', '下游保护'))
    }
  }

  private pulseMarker(pos: [number, number], color: string, label: string) {
    return new this.AMap.Marker({
      position: pos,
      content: `<div class="us-node" style="--c:${color}"><span>${label}</span></div>`,
      offset: new this.AMap.Pixel(-8, -8),
      clickable: true,
    })
  }

  private startParticles() {
    const step = () => {
      for (const p of this.particles) {
        p.t += p.speed
        if (p.t > 1) p.t = 0
        p.marker.setPosition(lerpPath(p.path, p.t))
      }
      this.rafId = requestAnimationFrame(step)
    }
    if (this.rafId == null) this.rafId = requestAnimationFrame(step)
  }

  resetToCity() {
    this.currentZoom = 11
    return flyTo(this.map, JINAN_CENTER, 11, 900)
  }
}

/** 沿折线按 t∈[0,1] 线性插值（纯函数，供测试）。 */
export function lerpPath(path: [number, number][], t: number): [number, number] {
  if (path.length === 0) return [0, 0]
  if (path.length === 1) return path[0]
  const clamped = Math.max(0, Math.min(1, t))
  const seg = clamped * (path.length - 1)
  const i = Math.min(Math.floor(seg), path.length - 2)
  const f = seg - i
  const a = path[i]
  const b = path[i + 1]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]
}
