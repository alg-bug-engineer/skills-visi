import {
  ARM_LEN,
  CW_GAP,
  CW_LEN,
  LANE_W,
  LOD_THRESHOLDS,
  MEDIAN_W,
  MOVE_COLOR,
  arrowSvg,
  calcBoxR,
  gatherArms,
  laneColor,
  laneLabel,
  metersToLngLat,
  parseLaneInfo,
  type ChannelArm,
  type ChannelLink,
  type LngLat,
} from './channelizationGeometry'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any
type Overlay = any

export interface ChannelizationScene {
  available?: boolean
  center?: LngLat | null
  links?: ChannelLink[]
}

function metricColor(value: number | null | undefined, kind: 'saturation' | 'queue' | 'green' | 'flow'): string {
  const v = Number(value)
  if (!Number.isFinite(v)) return '#6dffb5'
  if (kind === 'green') return v < 0.55 ? '#ffb020' : '#6dffb5'
  if (kind === 'flow') return v >= 800 ? '#29b6f6' : v >= 400 ? '#4dd0e1' : '#80deea'
  if (v >= 1 || (kind === 'queue' && v >= 180)) return '#ff3311'
  if (v >= 0.85 || (kind === 'queue' && v >= 120)) return '#ff8800'
  if (v >= 0.65 || (kind === 'queue' && v >= 60)) return '#fbbf24'
  return '#6dffb5'
}

function metricText(metrics: Record<string, number | null | undefined> | undefined): string {
  if (!metrics) return ''
  const chunks: string[] = []
  if (metrics.saturation != null) chunks.push(`饱和 ${Number(metrics.saturation).toFixed(2)}`)
  if (metrics.queue_m != null) chunks.push(`排队 ${Number(metrics.queue_m).toFixed(0)}m`)
  if (metrics.green_utilization != null) chunks.push(`绿用 ${(Number(metrics.green_utilization) * 100).toFixed(0)}%`)
  if (metrics.flow_vph != null) chunks.push(`流量 ${Number(metrics.flow_vph).toFixed(0)}`)
  return chunks.slice(0, 2).join(' · ')
}

export class ChannelizationLayer {
  private amap: AMapNS
  private map: AMapMap
  private center: LngLat
  private arms: ChannelArm[]
  private boxR: number
  private base: Array<{ lod: 'L0' | 'L1' | 'L2'; o: Overlay }> = []
  private labels: Overlay[] = []
  private currentLevel: string | null = null

  constructor(amap: AMapNS, map: AMapMap, scene: ChannelizationScene) {
    this.amap = amap
    this.map = map
    this.center = scene.center ?? [0, 0]
    this.arms = gatherArms(scene.links ?? [])
    this.boxR = calcBoxR(this.arms)
  }

  private ll(u: number, v: number, bearing: number): LngLat {
    return metersToLngLat(this.center, u, v, bearing)
  }

  private rect(arm: ChannelArm, u0: number, u1: number, v0: number, v1: number): LngLat[] {
    const b = arm.angle
    return [this.ll(u0, v0, b), this.ll(u1, v0, b), this.ll(u1, v1, b), this.ll(u0, v1, b)]
  }

  private addBase(lod: 'L0' | 'L1' | 'L2', overlay: Overlay) {
    this.base.push({ lod, o: overlay })
    this.map.add(overlay)
  }

  private addLabel(overlay: Overlay) {
    this.labels.push(overlay)
    this.map.add(overlay)
  }

  render() {
    if (!this.arms.length) return
    this.buildHalo()
    this.buildRoadCenterlines()
    for (const arm of this.arms) this.buildArm(arm)
    this.applyLOD(this.map.getZoom?.() ?? 18)
  }

  private armLinks(key: 'inLink' | 'outLink'): ChannelLink[] {
    return this.arms.map((arm) => arm[key]).filter((link): link is ChannelLink => Boolean(link))
  }

  private buildHalo() {
    this.addBase(
      'L0',
      new this.amap.Circle({
        center: this.center,
        radius: this.boxR + 8,
        strokeColor: '#38bdf8',
        strokeWeight: 2,
        strokeOpacity: 0.85,
        strokeStyle: 'dashed',
        fillColor: '#38bdf8',
        fillOpacity: 0.05,
        bubble: true,
        zIndex: 12,
      }),
    )
  }

  private buildRoadCenterlines() {
    for (const link of [...this.armLinks('inLink'), ...this.armLinks('outLink')]) {
      const path = link.path ?? []
      if (path.length < 2) continue
      this.addBase(
        'L1',
        new this.amap.Polyline({
          path,
          strokeColor: String(link.link_role).toLowerCase() === 'exit' ? '#3a4757' : '#4b5b6e',
          strokeWeight: 2,
          strokeOpacity: 0.55,
          bubble: true,
          zIndex: 20,
        }),
      )
    }
  }

  private buildArm(arm: ChannelArm) {
    const b = arm.angle
    const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : []
    const nIn = inLanes.length
    const nOut = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : 0
    if (nIn + nOut === 0) return
    const u0 = this.boxR
    const u1 = this.boxR + ARM_LEN
    const wIn = nIn * LANE_W
    const wOut = nOut * LANE_W

    this.addBase(
      'L1',
      new this.amap.Polygon({
        path: this.rect(arm, u0, u1, -wIn - MEDIAN_W, wOut + MEDIAN_W),
        strokeColor: '#1f2937',
        strokeWeight: 1,
        strokeOpacity: 0.8,
        fillColor: '#39424f',
        fillOpacity: 0.5,
        bubble: true,
        zIndex: 14,
      }),
    )

    for (let i = 0; i < nIn; i++) {
      const vIn = -(i * LANE_W)
      const vOut = -((i + 1) * LANE_W)
      const code = inLanes[i]
      this.addBase(
        'L2',
        new this.amap.Polygon({
          path: this.rect(arm, u0, u1, vOut, vIn),
          strokeOpacity: 0,
          fillColor: laneColor(code),
          fillOpacity: 0.5,
          bubble: true,
          zIndex: 16,
        }),
      )
      if (i > 0) {
        this.addBase(
          'L2',
          new this.amap.Polyline({
            path: [this.ll(u0, vIn, b), this.ll(u1, vIn, b)],
            strokeColor: '#e5e7eb',
            strokeWeight: 1.6,
            strokeOpacity: 0.8,
            strokeStyle: 'dashed',
            strokeDasharray: [9, 9],
            bubble: true,
            zIndex: 18,
          }),
        )
      }
      const ac = this.ll(u0 + 9, (vIn + vOut) / 2, b)
      this.addBase(
        'L2',
        new this.amap.Marker({
          position: ac,
          offset: new this.amap.Pixel(-16, -22),
          bubble: true,
          zIndex: 30,
          angle: (b + 180) % 360,
          icon: new this.amap.Icon({
            image: arrowSvg(code, '#f8fafc'),
            size: new this.amap.Size(32, 44),
            imageSize: new this.amap.Size(32, 44),
          }),
        }),
      )
    }

    for (let j = 0; j < nOut; j++) {
      const vIn = j * LANE_W
      const vOut = (j + 1) * LANE_W
      this.addBase(
        'L2',
        new this.amap.Polygon({
          path: this.rect(arm, u0, u1, vIn, vOut),
          strokeOpacity: 0,
          fillColor: MOVE_COLOR.exit,
          fillOpacity: 0.28,
          bubble: true,
          zIndex: 15,
        }),
      )
      if (j > 0) {
        this.addBase(
          'L2',
          new this.amap.Polyline({
            path: [this.ll(u0, vIn, b), this.ll(u1, vIn, b)],
            strokeColor: '#cbd5e1',
            strokeWeight: 1.4,
            strokeOpacity: 0.6,
            strokeStyle: 'dashed',
            strokeDasharray: [9, 9],
            bubble: true,
            zIndex: 18,
          }),
        )
      }
    }

    for (const off of [-MEDIAN_W * 0.45, MEDIAN_W * 0.45]) {
      this.addBase(
        'L2',
        new this.amap.Polyline({
          path: [this.ll(u0, off, b), this.ll(u1, off, b)],
          strokeColor: '#fbbf24',
          strokeWeight: 2,
          strokeOpacity: 0.95,
          bubble: true,
          zIndex: 19,
        }),
      )
    }

    if (nIn > 0) {
      this.addBase(
        'L2',
        new this.amap.Polyline({
          path: [this.ll(u0, 0, b), this.ll(u0, -wIn, b)],
          strokeColor: '#f8fafc',
          strokeWeight: 5,
          strokeOpacity: 0.95,
          bubble: true,
          zIndex: 20,
        }),
      )
    }

    const total = wIn + wOut + 2 * MEDIAN_W
    const vS = -wIn - MEDIAN_W
    const cu0 = this.boxR - CW_GAP - CW_LEN
    const cu1 = this.boxR - CW_GAP
    for (let v = vS; v < vS + total; v += 1.9) {
      this.addBase(
        'L2',
        new this.amap.Polygon({
          path: [this.ll(cu0, v, b), this.ll(cu1, v, b), this.ll(cu1, v + 1.05, b), this.ll(cu0, v + 1.05, b)],
          strokeOpacity: 0,
          fillColor: '#e8edf2',
          fillOpacity: 0.82,
          bubble: true,
          zIndex: 17,
        }),
      )
    }

    this.buildMetricLabels(arm)
  }

  private buildMetricLabels(arm: ChannelArm) {
    const link = arm.inLink
    if (!link) return
    const metrics = link.metrics ?? {}
    const text = metricText(metrics)
    if (!text) return
    const lanes = parseLaneInfo(link)
    const nIn = lanes.length
    const wIn = nIn * LANE_W
    const u0 = this.boxR
    const sat = metrics.saturation
    const queue = metrics.queue_m
    const color = sat != null ? metricColor(sat, 'saturation') : queue != null ? metricColor(queue, 'queue') : '#6dffb5'
    const fillLen =
      queue != null
        ? Math.min(ARM_LEN * 0.92, Math.max(2, Number(queue)))
        : ARM_LEN * 0.55 * Math.min(Math.max(Number(sat ?? 0.5), 0.12), 1)

    this.addBase(
      'L2',
      new this.amap.Polygon({
        path: this.rect(arm, u0, u0 + fillLen, -wIn, 0),
        strokeOpacity: 0,
        fillColor: color,
        fillOpacity: 0.46,
        bubble: true,
        zIndex: 44,
      }),
    )

    const labelPos = this.ll(u0 + Math.min(fillLen, ARM_LEN * 0.48), -wIn / 2, arm.angle)
    const laneSummary = lanes.map(laneLabel).slice(0, 3).join('/')
    this.addLabel(
      new this.amap.Marker({
        position: labelPos,
        content:
          `<div class="channel-metric-label" style="border-color:${color};color:${color}">` +
          `<strong>${link.dir8_label ?? '进口'} ${laneSummary}</strong><span>${text}</span></div>`,
        offset: new this.amap.Pixel(0, 0),
        bubble: true,
        zIndex: 62,
      }),
    )
  }

  applyLOD(zoom: number) {
    const level = zoom < LOD_THRESHOLDS.L1 ? 'L0' : zoom < LOD_THRESHOLDS.L2 ? 'L1' : 'L2'
    if (level === this.currentLevel) return
    this.currentLevel = level
    const showL1 = level === 'L1' || level === 'L2'
    const showL2 = level === 'L2'
    for (const { lod, o } of this.base) {
      const visible = lod === 'L0' ? true : lod === 'L1' ? showL1 : showL2
      if (visible) o.show?.()
      else o.hide?.()
    }
    for (const marker of this.labels) {
      if (showL2) marker.show?.()
      else marker.hide?.()
    }
  }

  dispose() {
    const overlays = [...this.base.map((item) => item.o), ...this.labels]
    if (overlays.length) this.map.remove(overlays)
    this.base = []
    this.labels = []
    this.currentLevel = null
  }
}
