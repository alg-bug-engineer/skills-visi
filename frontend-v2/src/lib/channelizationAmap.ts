/**
 * channelizationAmap.ts
 *
 * 基于高德地图(AMap)矢量覆盖物的路口渠化渲染器，替代 channelizationLayer.js(THREE)。
 * 完整复刻：静态渠化（车道面/虚线/停止线/斑马线/转向箭头/转角圆弧/真实中心线）
 * 与四套阶段标注（applyCheckHighlight / applyTurnHighlight /
 * applyDirectionRoleHighlight / applyArmSceneLabels）。
 *
 * 依赖注入：构造时传入 AMap 命名空间与 map 实例，便于单测用 stub。
 */
import {
  ARM_LEN,
  CW_GAP,
  CW_LEN,
  LANE_W,
  LOD_THRESHOLDS,
  MEDIAN_W,
  MOVE_COLOR,
  type ChannelArm,
  type ChannelLink,
  arrowSvg,
  calcBoxR,
  gatherArms,
  laneColor,
  laneLabel,
  metersToLngLat,
  parseLaneInfo,
} from './channelizationGeometry'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any
type Overlay = any
type LonLat = [number, number]

export interface ChannelInterItem {
  intersection_info: { longitude: number; latitude: number; name?: string }
  surrounding_links: {
    进入路口的路段: ChannelLink[]
    离开路口的路段: ChannelLink[]
  }
}

export interface TurnHighlightSpec {
  dir: string
  turnCode: string
  label?: string
  saturation?: number
}

export interface ArmSceneLabel {
  dir: string
  line1?: string
  line2?: string
  colorHex?: string
}

export type HighlightEvidence = Record<string, number | null | undefined>

/* ── 方向匹配（移植 _armMatchesDir，仅 N/E/S/W） ───────────────────────────── */
const DIR_BEARING: Record<string, number> = { 北: 0, 东: 90, 南: 180, 西: 270 }
function armMatchesDir(armAngle: number, dir: string): boolean {
  const target = DIR_BEARING[dir]
  if (target == null) return false
  const d = Math.abs((((armAngle - target + 540) % 360) - 180))
  return d <= 28
}

/* ── 指标文案（移植 _metricLabel） ────────────────────────────────────────── */
function metricLabel(indicatorId: string, ev: HighlightEvidence): string | null {
  const id = indicatorId || ''
  if (id.includes('saturation')) {
    const v = ev.saturation_max ?? ev.max_turn_saturation
    return v != null ? `饱和度 ${Number(v).toFixed(3)}` : '饱和度指标'
  }
  if (id.includes('unbalance') || id.includes('imbalance')) {
    const v = ev.unbalance_index ?? ev.turn_imbalance_ratio
    return v != null ? `失衡指数 ${Number(v).toFixed(3)}` : '流量失衡'
  }
  if (id.includes('green') || id.includes('signal')) {
    const v = ev.avg_green_ratio
    return v != null ? `绿信比 ${(Number(v) * 100).toFixed(1)}%` : '信控指标'
  }
  if (id.includes('jam') || id.includes('delay') || id.includes('congestion') || id.includes('nearby')) {
    const v = ev.avg_jam_delay_index ?? ev.avg_delay_dur
    return v != null ? `延误/拥堵 ${Number(v).toFixed(2)}` : '拥堵指标'
  }
  if (id.includes('capacity')) return '通行能力'
  if (id.includes('device')) return '设备覆盖'
  const firstKey = Object.keys(ev).find(
    (k) => !['expression', 'business_metric', 'frequency', 'common_periods', 'value'].includes(k) && ev[k] != null,
  )
  if (firstKey) return `${firstKey}: ${ev[firstKey]}`
  return null
}

const VERDICT_COLOR: Record<string, string> = {
  fail: '#ff3311',
  warn: '#ff8800',
  partial: '#8888cc',
  pass: '#00cc66',
}
const VERDICT_ALPHA: Record<string, number> = { fail: 0.42, warn: 0.3, partial: 0.18, pass: 0.18 }
const VERDICT_TEXT: Record<string, string> = {
  fail: '⚠ 异常超阈值',
  warn: '⚠ 告警',
  partial: '○ 数据缺失',
  pass: '✓ 正常',
}

function flattenLinks(interItem: ChannelInterItem): ChannelLink[] {
  const sl = interItem.surrounding_links || ({} as ChannelInterItem['surrounding_links'])
  const ins = (sl['进入路口的路段'] || []).map((l) => ({ ...l, link_role: 'entrance' }))
  const outs = (sl['离开路口的路段'] || []).map((l) => ({ ...l, link_role: 'exit' }))
  return [...ins, ...outs]
}

export class ChannelizationAmapLayer {
  private amap: AMapNS
  private map: AMapMap
  center: LonLat
  name: string
  arms: ChannelArm[]
  boxR: number
  /** 静态渠化覆盖物，按 LOD 显隐 */
  private base: Array<{ lod: 'L0' | 'L1' | 'L2'; o: Overlay }> = []
  /** 阶段标注覆盖物，整组清除 */
  private highlight: Overlay[] = []
  private currentLevel: string | null = null

  constructor(amap: AMapNS, map: AMapMap, interItem: ChannelInterItem) {
    this.amap = amap
    this.map = map
    this.center = [interItem.intersection_info.longitude, interItem.intersection_info.latitude]
    this.name = interItem.intersection_info.name || ''
    const links = flattenLinks(interItem)
    this.arms = gatherArms(links)
    this.boxR = calcBoxR(this.arms)
  }

  /* ── 工具 ──────────────────────────────────────────────────────────────── */
  private ll(u: number, v: number, bearing: number): LonLat {
    return metersToLngLat(this.center, u, v, bearing)
  }
  private addBase(lod: 'L0' | 'L1' | 'L2', o: Overlay) {
    this.base.push({ lod, o })
    this.map.add(o)
  }
  private addHl(o: Overlay) {
    this.highlight.push(o)
    this.map.add(o)
  }
  /** 臂局部矩形 [u0,u1]×[v0,v1] → 经纬度多边形路径 */
  private rect(arm: ChannelArm, u0: number, u1: number, v0: number, v1: number): LonLat[] {
    const b = arm.angle
    return [this.ll(u0, v0, b), this.ll(u1, v0, b), this.ll(u1, v1, b), this.ll(u0, v1, b)]
  }

  /* ── 静态渠化 ──────────────────────────────────────────────────────────── */
  render() {
    this.buildHalo()
    this.buildRoadCenterlines()
    for (const arm of this.arms) this.buildArm(arm)
    this.buildCorners()
    this.applyLOD(this.map.getZoom())
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
    const links = [
      ...(this.armLinks('inLink')),
      ...(this.armLinks('outLink')),
    ]
    for (const lk of links) {
      const path = lk.path && lk.path.length ? lk.path : []
      if (path.length < 2) continue
      this.addBase(
        'L1',
        new this.amap.Polyline({
          path,
          strokeColor: lk.link_role === 'exit' ? '#3a4757' : '#4b5b6e',
          strokeWeight: 2,
          strokeOpacity: 0.55,
          bubble: true,
          zIndex: 20,
        }),
      )
    }
  }

  private armLinks(key: 'inLink' | 'outLink'): ChannelLink[] {
    return this.arms.map((a) => a[key]).filter((l): l is ChannelLink => Boolean(l))
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

    // 整体路面（L1）
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

    // 进口车道面 + 分隔虚线 + 箭头（L2）
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

    // 出口车道面 + 分隔虚线（L2）
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

    // 中央黄色双实线（L2）
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

    // 停止线（L2）
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

    // 人行横道（L2）
    const total = wIn + wOut + 2 * MEDIAN_W
    const vS = -wIn - MEDIAN_W
    const cu0 = this.boxR - CW_GAP - CW_LEN
    const cu1 = this.boxR - CW_GAP
    const step = 1.9
    for (let v = vS; v < vS + total; v += step) {
      this.addBase(
        'L2',
        new this.amap.Polygon({
          path: [
            this.ll(cu0, v, b),
            this.ll(cu1, v, b),
            this.ll(cu1, v + step * 0.55, b),
            this.ll(cu0, v + step * 0.55, b),
          ],
          strokeOpacity: 0,
          fillColor: '#e8edf2',
          fillOpacity: 0.82,
          bubble: true,
          zIndex: 17,
        }),
      )
    }
  }

  private buildCorners() {
    const sorted = [...this.arms].sort((a, b) => a.angle - b.angle)
    const c = this.center
    for (let i = 0; i < sorted.length; i++) {
      const a1 = sorted[i]
      const a2 = sorted[(i + 1) % sorted.length]
      const nOut1 = a1.outLink ? a1.outLink.c_lane_num || a1.outLink.lane_num || 0 : 0
      const nIn2 = a2.inLink ? parseLaneInfo(a2.inLink).length : 0
      const p1 = metersToLngLat(c, this.boxR, nOut1 * LANE_W + MEDIAN_W, a1.angle)
      const p2 = metersToLngLat(c, this.boxR, -(nIn2 * LANE_W) - MEDIAN_W, a2.angle)
      const pts: LonLat[] = []
      for (let k = 0; k <= 16; k++) {
        const t = k / 16
        const it = 1 - t
        pts.push([
          it * it * p1[0] + 2 * it * t * c[0] + t * t * p2[0],
          it * it * p1[1] + 2 * it * t * c[1] + t * t * p2[1],
        ])
      }
      this.addBase(
        'L2',
        new this.amap.Polyline({ path: pts, strokeColor: '#ffffff', strokeWeight: 2, strokeOpacity: 0.7, bubble: true, zIndex: 18 }),
      )
    }
  }

  /* ── LOD ───────────────────────────────────────────────────────────────── */
  applyLOD(zoom: number) {
    const level = zoom < LOD_THRESHOLDS.L1 ? 'L0' : zoom < LOD_THRESHOLDS.L2 ? 'L1' : 'L2'
    if (level === this.currentLevel) return
    this.currentLevel = level
    const showL1 = level === 'L1' || level === 'L2'
    const showL2 = level === 'L2'
    for (const { lod, o } of this.base) {
      const vis = lod === 'L0' ? true : lod === 'L1' ? showL1 : showL2
      if (vis) o.show()
      else o.hide()
    }
  }
  getLevel(): string | null {
    return this.currentLevel
  }

  /* ── 文本框（复刻 _makeTextTex：圆角深底 + 彩色边框 + 双行） ────────────── */
  private addTextMarker(pos: LonLat, line1: string, line2: string, colorHex: string, offsetY = -28) {
    const content =
      `<div style="transform:translate(-50%,${offsetY}px);min-width:120px;padding:6px 12px;` +
      `background:rgba(0,4,14,0.82);border:2px solid ${colorHex};border-radius:10px;` +
      `text-align:center;font-family:'Microsoft YaHei',sans-serif;white-space:nowrap;` +
      `box-shadow:0 4px 14px rgba(0,0,0,0.45);pointer-events:none;">` +
      `<div style="font-weight:700;font-size:14px;color:${colorHex};line-height:1.4;">${line1}</div>` +
      (line2 ? `<div style="font-size:11px;color:rgba(220,240,255,0.85);line-height:1.4;">${line2}</div>` : '') +
      `</div>`
    this.addHl(
      new this.amap.Marker({
        position: pos,
        content,
        offset: new this.amap.Pixel(0, 0),
        bubble: true,
        zIndex: 60,
      }),
    )
  }

  clearHighlight() {
    if (this.highlight.length) {
      this.map.remove(this.highlight)
      this.highlight = []
    }
  }

  /* ── applyCheckHighlight（饱和度/失衡/信控 强调面 + 色带 + 文本框） ──────── */
  applyCheckHighlight(indicatorId: string, verdict: string, evidence: HighlightEvidence) {
    this.clearHighlight()
    if (!this.arms.length) return
    const id = indicatorId || ''
    const ev = evidence || {}
    const isSat = id.includes('saturation') || id.includes('capacity') || id.includes('demand')
    const isImb = id.includes('unbalance') || id.includes('imbalance')
    const isSig = id.includes('signal') || id.includes('green')
    const isCong = id.includes('jam') || id.includes('congestion') || id.includes('nearby') || id.includes('delay')
    const colorHex = VERDICT_COLOR[verdict] ?? VERDICT_COLOR.pass
    const baseAlpha = VERDICT_ALPHA[verdict] ?? 0.18

    for (const arm of this.arms) {
      const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : []
      const nIn = inLanes.length
      const nOut = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : 0
      if (nIn + nOut === 0) continue
      const u0 = this.boxR
      const u1 = this.boxR + ARM_LEN
      const wIn = nIn * LANE_W
      const wOut = nOut * LANE_W

      // 路面彩色强调面
      this.addHl(
        new this.amap.Polygon({
          path: this.rect(arm, u0, u1, -wIn - MEDIAN_W, wOut + MEDIAN_W),
          strokeOpacity: 0,
          fillColor: colorHex,
          fillOpacity: baseAlpha,
          bubble: true,
          zIndex: 40,
        }),
      )

      // 饱和度/拥堵：从停止线向外的排队色带 + 末端线
      if ((isSat || isCong) && nIn > 0) {
        const satVal = Math.min(
          Number(ev.saturation_max ?? ev.max_turn_saturation ?? ev.avg_jam_delay_index ?? 0.9),
          1.8,
        )
        const fillLen = ARM_LEN * 0.88 * Math.min(satVal / 1.0, 1.0)
        if (fillLen > 1) {
          const flowColor = satVal >= 1.0 ? '#ff1100' : satVal >= 0.85 ? '#ff5500' : '#ffaa00'
          this.addHl(
            new this.amap.Polygon({
              path: this.rect(arm, u0, u0 + fillLen, -wIn, 0),
              strokeOpacity: 0,
              fillColor: flowColor,
              fillOpacity: 0.5,
              bubble: true,
              zIndex: 42,
            }),
          )
          this.addHl(
            new this.amap.Polyline({
              path: [this.ll(u0 + fillLen, 0, arm.angle), this.ll(u0 + fillLen, -wIn, arm.angle)],
              strokeColor: '#ff2200',
              strokeWeight: 3,
              strokeOpacity: 0.9,
              bubble: true,
              zIndex: 43,
            }),
          )
        }
      }

      // 信控：停止线处绿/红信比色带
      if (isSig && nIn > 0) {
        const ratio = Math.min(Number(ev.avg_green_ratio ?? 0.5), 1.0)
        const greenW = wIn * ratio
        if (greenW > 0.2) {
          this.addHl(
            new this.amap.Polygon({
              path: this.rect(arm, u0, u0 + 3, -greenW, 0),
              strokeOpacity: 0,
              fillColor: '#00ee44',
              fillOpacity: 0.8,
              bubble: true,
              zIndex: 44,
            }),
          )
        }
        if (wIn - greenW > 0.2) {
          this.addHl(
            new this.amap.Polygon({
              path: this.rect(arm, u0, u0 + 3, -wIn, -greenW),
              strokeOpacity: 0,
              fillColor: '#ff2200',
              fillOpacity: 0.8,
              bubble: true,
              zIndex: 44,
            }),
          )
        }
      }

      // 失衡：进口色带
      if (isImb && nIn > 0 && nOut > 0) {
        const idx = Number(ev.unbalance_index ?? ev.turn_imbalance_ratio ?? 0.2)
        const scale = Math.min(idx / 0.5, 1.0)
        const inW = wIn * (0.7 + scale * 0.25)
        this.addHl(
          new this.amap.Polygon({
            path: this.rect(arm, u0, u0 + ARM_LEN * 0.65, -inW, 0),
            strokeOpacity: 0,
            fillColor: '#ff4400',
            fillOpacity: 0.4,
            bubble: true,
            zIndex: 42,
          }),
        )
      }
    }

    // 浮空文本框
    const text = metricLabel(id, ev)
    if (text) {
      this.addTextMarker(this.center, text, VERDICT_TEXT[verdict] ?? '', colorHex, -40)
    }
  }

  /* ── applyTurnHighlight（指定进口转向：车道色带 + 黄环 + 文本框） ───────── */
  applyTurnHighlight(spec: TurnHighlightSpec) {
    this.clearHighlight()
    if (!this.arms.length || !spec?.dir || !spec?.turnCode) return
    for (const arm of this.arms) {
      if (!armMatchesDir(arm.angle, spec.dir)) continue
      const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : []
      const laneIdx = inLanes.findIndex((code) => code === spec.turnCode)
      if (laneIdx < 0) continue
      const u0 = this.boxR
      const vIn = -(laneIdx * LANE_W)
      const vOut = -((laneIdx + 1) * LANE_W)
      const sat = spec.saturation != null ? Number(spec.saturation) : 1.0
      const flowColor = sat >= 1.0 ? '#ff1100' : sat >= 0.85 ? '#ff5500' : '#ffaa00'
      this.addHl(
        new this.amap.Polygon({
          path: this.rect(arm, u0, u0 + ARM_LEN * 0.75, vOut, vIn),
          strokeOpacity: 0,
          fillColor: flowColor,
          fillOpacity: 0.72,
          bubble: true,
          zIndex: 46,
        }),
      )
      const ringPos = this.ll(u0 + ARM_LEN * 0.28, (vIn + vOut) / 2, arm.angle)
      this.addHl(
        new this.amap.CircleMarker({
          center: ringPos,
          radius: 12,
          strokeColor: '#ffdd00',
          strokeWeight: 4,
          strokeOpacity: 0.95,
          fillOpacity: 0,
          bubble: true,
          zIndex: 47,
        }),
      )
      const label = spec.label || `${spec.dir}向转向`
      const satText = spec.saturation != null ? `饱和度 ${(spec.saturation * 100).toFixed(0)}%` : '重点关注'
      this.addTextMarker(this.center, label, satText, '#ffcc00', -40)
      break
    }
  }

  /* ── applyDirectionRoleHighlight（关注橙红/保护绿/其他 dim） ────────────── */
  applyDirectionRoleHighlight(focusDirs: string[] = [], protectDirs: string[] = []) {
    this.clearHighlight()
    if (!focusDirs.length && !protectDirs.length) return
    for (const arm of this.arms) {
      const isFocus = focusDirs.some((d) => armMatchesDir(arm.angle, d))
      const isProtect = protectDirs.some((d) => armMatchesDir(arm.angle, d))
      const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : []
      const nIn = inLanes.length
      const nOut = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : 0
      if (nIn + nOut === 0) continue
      const u0 = this.boxR
      const u1 = this.boxR + ARM_LEN
      const wIn = nIn * LANE_W
      const wOut = nOut * LANE_W
      let color = '#4a5568'
      let opacity = 0.12
      if (isFocus) {
        color = '#ff6b4a'
        opacity = 0.42
      } else if (isProtect) {
        color = '#6dffb5'
        opacity = 0.32
      } else {
        opacity = 0.1
      }
      this.addHl(
        new this.amap.Polygon({
          path: this.rect(arm, u0, u1, -wIn - MEDIAN_W, wOut + MEDIAN_W),
          strokeOpacity: 0,
          fillColor: color,
          fillOpacity: opacity,
          bubble: true,
          zIndex: 38,
        }),
      )
    }
  }

  /* ── applyArmSceneLabels（臂外缘文本框） ──────────────────────────────────── */
  applyArmSceneLabels(labels: ArmSceneLabel[] = []) {
    // 臂标签与强调可叠加，这里单独清除上一批臂标签（用同一 highlight 池，调用方负责顺序）
    if (!labels.length) return
    for (const label of labels) {
      if (!label.dir) continue
      const arm = this.arms.find((a) => armMatchesDir(a.angle, label.dir))
      if (!arm) continue
      const pos = this.ll(this.boxR + ARM_LEN * 0.94, 0, arm.angle)
      this.addTextMarker(pos, label.line1 || '', label.line2 || '', label.colorHex || '#00e5ff', -10)
    }
  }

  /* ── 销毁 ──────────────────────────────────────────────────────────────── */
  dispose() {
    this.clearHighlight()
    if (this.base.length) {
      this.map.remove(this.base.map((b) => b.o))
      this.base = []
    }
    this.currentLevel = null
  }
}

export { armMatchesDir, metricLabel, laneLabel }
