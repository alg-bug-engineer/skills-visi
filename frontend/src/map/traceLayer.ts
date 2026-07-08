/**
 * 单链路流量溯源渲染层。
 *
 * 呈现逻辑严格对齐 references/流量溯源 lib/upstreamTraceLayer.ts：
 * 发光双层干线（外层 glow + 亮核 + showDir）、按占比缩放的脉冲节点、
 * 可点开的极简占比标签。**仅配色对齐本项目主题**，其余口径（线宽随占比、
 * zIndex 分层、按 id 幂等注册、reset/dispose 释放）与参考一致。
 *
 * 取数：只消费后端真实 path/坐标/share_pct（rule 19，禁止前端合成）。
 */
import { type LngLat } from './traceParticles'
import {
  buildUpstreamLabelHtml,
  coverageNodeStyle,
  turnLabelFromMovement,
  upstreamEdgeStrokeWeight,
} from './traceLabels'
import {
  isEntranceLink,
  sniffCoverage,
  sniffLinkPath,
  sniffNodeId,
  shouldRenderSniffNode,
  type SniffTraceDirection,
  type TraceSniffIntersection,
  type TraceSniffScene,
} from './traceSniff'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any
type Overlay = any

/** 干线发光配色：上游琥珀暖色 / 下游青蓝冷色（对齐参考，落到本项目主题）。 */
const TRACE_PALETTE = {
  upstream: { glow: '#f5a623', core: '#ffcf7a' },
  downstream: { glow: '#0ea5e9', core: '#38bdf8' },
} as const

const SNIFF_PALETTE = {
  target: { glow: '#22c55e', core: '#86efac' },
  upstreamMain: { glow: '#f59e0b', core: '#fbbf24' },
  upstreamOther: { glow: '#3b82f6', core: '#93c5fd' },
  downstreamMain: { glow: '#a855f7', core: '#d8b4fe' },
  downstreamOther: { glow: '#06b6d4', core: '#67e8f9' },
} as const

export type TraceDirection = keyof typeof TRACE_PALETTE

const LABEL_OFFSET: [number, number] = [10, -48]

export interface UpstreamTraceItem {
  upstream_inter_id?: string | null
  upstream_inter_name?: string | null
  upstream_lng?: number | null
  upstream_lat?: number | null
  dir8_code?: number | null
  path?: LngLat[]
  dominant_movement?: { turn?: string; share_pct?: number | null } | null
  upstream_movements?: Array<{ turn?: string; share_pct?: number | null }>
}

export interface DownstreamTraceItem {
  downstream_inter_id?: string | null
  name?: string | null
  movement?: string | null
  share_pct?: number | null
  path?: LngLat[]
  lon?: number | null
  lat?: number | null
  capacity?: { blocked?: boolean } | null
}

export class TraceLayer {
  private readonly AMap: AMapNS
  private readonly map: AMapMap
  private readonly byId = new Map<string, Overlay[]>()
  private readonly fitList: Overlay[] = []
  private readonly labelMarkers = new Map<string, any>()
  private readonly openLabelIds = new Set<string>()

  constructor(amap: AMapNS, map: AMapMap) {
    this.AMap = amap
    this.map = map
  }

  private register(id: string, overlay: Overlay): void {
    overlay.setMap(this.map)
    const list = this.byId.get(id) ?? []
    list.push(overlay)
    this.byId.set(id, list)
    this.fitList.push(overlay)
  }

  /** 发光干线：外层低透 glow + 亮核线（末段带方向）。 */
  revealEdge(
    id: string,
    path: LngLat[],
    opts: { flowPct?: number | null; traceKind?: TraceDirection } = {},
  ): void {
    if (this.byId.has(id) || path.length < 2) return
    const weight = upstreamEdgeStrokeWeight(opts.flowPct)
    const colors = TRACE_PALETTE[opts.traceKind ?? 'upstream']

    const glow = new this.AMap.Polyline({
      path,
      strokeColor: colors.glow,
      strokeWeight: weight * 3,
      strokeOpacity: 0.2,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: opts.traceKind === 'downstream' ? 70 : 68,
    })
    const core = new this.AMap.Polyline({
      path,
      strokeColor: colors.core,
      strokeWeight: weight,
      strokeOpacity: 0.95,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: true,
      zIndex: opts.traceKind === 'downstream' ? 74 : 72,
    })
    this.register(id, glow)
    this.register(id, core)
  }

  private sniffColors(
    node: TraceSniffIntersection,
    traceDirection: SniffTraceDirection,
  ): { glow: string; core: string } {
    if (node.role === 'target') return SNIFF_PALETTE.target
    if (traceDirection === 'downstream') {
      return node.in_main_corridor ? SNIFF_PALETTE.downstreamMain : SNIFF_PALETTE.downstreamOther
    }
    return node.in_main_corridor ? SNIFF_PALETTE.upstreamMain : SNIFF_PALETTE.upstreamOther
  }

  private revealSniffLink(
    id: string,
    path: LngLat[],
    opts: {
      node: TraceSniffIntersection
      traceDirection: SniffTraceDirection
      linkRole?: string | null
    },
  ): void {
    if (this.byId.has(id) || path.length < 2) return
    const colors = this.sniffColors(opts.node, opts.traceDirection)
    const isTarget = opts.node.role === 'target'
    const isMain = Boolean(opts.node.in_main_corridor)
    const entrance = isEntranceLink(opts.linkRole)
    const coverage = sniffCoverage(opts.node)
    const weight = isTarget ? (entrance ? 3 : 2.4) : upstreamEdgeStrokeWeight(coverage)
    const zBase = isTarget ? 62 : isMain ? 72 : 56

    const glow = new this.AMap.Polyline({
      path,
      strokeColor: colors.glow,
      strokeWeight: isTarget ? weight * 2.2 : weight * 3,
      strokeOpacity: isTarget ? 0.18 : 0.22,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: zBase,
    })
    const core = new this.AMap.Polyline({
      path,
      strokeColor: colors.core,
      strokeWeight: weight,
      strokeOpacity: isTarget ? (entrance ? 0.55 : 0.32) : 0.92,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: !isTarget,
      zIndex: zBase + 2,
    })
    this.register(id, glow)
    this.register(`${id}:core`, core)
  }

  private nodeContent(
    role: 'target' | 'upstream' | 'downstream' | 'governance',
    coverage?: number | null,
  ): string {
    const roleCls =
      role === 'target' ? 'is-target' : role === 'governance' ? 'is-gov' : role === 'downstream' ? 'is-down' : ''
    if (role === 'target' || coverage == null || !Number.isFinite(coverage)) {
      return `<div class="trace-node ${roleCls}"></div>`
    }
    const { size, opacity, glow } = coverageNodeStyle(coverage)
    const shadow = (14 * glow).toFixed(1)
    const shadowOuter = (34 * glow).toFixed(1)
    const alpha = (0.78 * glow).toFixed(2)
    const alphaOuter = (0.26 * glow).toFixed(2)
    const rgb = role === 'downstream' ? '14,165,233' : '245,166,35'
    return (
      `<div class="trace-node is-scaled ${roleCls}" ` +
      `style="width:${size}px;height:${size}px;opacity:${opacity.toFixed(2)};` +
      `box-shadow:0 0 ${shadow}px rgba(${rgb},${alpha}),0 0 ${shadowOuter}px rgba(${rgb},${alphaOuter})">` +
      `</div>`
    )
  }

  /** 节点脉冲：目标=红、上游=琥珀、下游=青蓝、治理落点=绿（由 CSS class 决定）。 */
  revealNode(
    id: string,
    lon: number,
    lat: number,
    opts: {
      role?: 'target' | 'upstream' | 'downstream' | 'governance'
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
      zIndex: role === 'target' ? 97 : 95,
      content: this.nodeContent(role, opts.coverage),
      cursor: clickable ? 'pointer' : undefined,
    })
    if (clickable && opts.onClick) marker.on('click', opts.onClick)
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

  private ensureLabel(nodeId: string, lon: number, lat: number, html: string, defaultOpen = false): void {
    if (this.labelMarkers.has(nodeId)) return
    const marker = new this.AMap.Marker({
      position: [lon, lat],
      anchor: 'center',
      offset: new this.AMap.Pixel(LABEL_OFFSET[0], LABEL_OFFSET[1]),
      zIndex: 96,
      content: html,
    })
    marker.setMap(null)
    this.labelMarkers.set(nodeId, marker)
    const key = `label:${nodeId}`
    const list = this.byId.get(key) ?? []
    list.push(marker)
    this.byId.set(key, list)
    this.fitList.push(marker)
    if (defaultOpen) this.setLabelVisible(nodeId, true)
  }

  /** 上游一跳来向：琥珀发光路径 + 占比缩放节点 + 可点开占比标签（缺占比显示「拓扑」）。 */
  renderUpstreamTraces(traces: UpstreamTraceItem[]): void {
    let topIdx = -1
    let topCov = -1
    traces.forEach((item, i) => {
      const cov = item.dominant_movement?.share_pct ?? item.upstream_movements?.[0]?.share_pct ?? null
      if (cov != null && Number.isFinite(cov) && cov > topCov) {
        topCov = cov
        topIdx = i
      }
    })

    traces.forEach((item, i) => {
      const path = (item.path ?? []).filter(Boolean) as LngLat[]
      const cov = item.dominant_movement?.share_pct ?? item.upstream_movements?.[0]?.share_pct ?? null
      const nodeId = String(item.upstream_inter_id ?? `up${i}`)
      if (path.length >= 2) {
        this.revealEdge(`up:${nodeId}`, path, { flowPct: cov, traceKind: 'upstream' })
      }
      if (item.upstream_lng != null && item.upstream_lat != null) {
        const label = buildUpstreamLabelHtml({
          name: String(item.upstream_inter_name ?? '上游'),
          coverage: cov,
        })
        this.revealNode(nodeId, item.upstream_lng, item.upstream_lat, {
          role: 'upstream',
          coverage: cov,
          clickable: true,
          onClick: () => this.toggleLabel(nodeId),
        })
        this.ensureLabel(nodeId, item.upstream_lng, item.upstream_lat, label, i === topIdx)
      }
    })
  }

  /** 下游一跳去向：青蓝发光路径 + 节点 + 占比标签（无占比显示「拓扑」；饱和显示为治理绿）。 */
  renderDownstreamTraces(traces: DownstreamTraceItem[]): void {
    for (const item of traces) {
      const path = (item.path ?? []).filter(Boolean) as LngLat[]
      const nodeId = String(item.downstream_inter_id ?? item.movement ?? path.length)
      const blocked = Boolean(item.capacity?.blocked)
      if (path.length >= 2) {
        this.revealEdge(`down:${nodeId}`, path, {
          flowPct: item.share_pct ?? undefined,
          traceKind: 'downstream',
        })
      }
      if (item.lon != null && item.lat != null) {
        this.revealNode(nodeId, item.lon, item.lat, {
          role: blocked ? 'governance' : 'downstream',
          coverage: item.share_pct ?? undefined,
          clickable: true,
          onClick: () => this.toggleLabel(nodeId),
        })
        const move = turnLabelFromMovement(item.movement)
        const share = item.share_pct != null && Number.isFinite(item.share_pct) ? `${item.share_pct}%` : '拓扑'
        const text = `${move ? `${move}→` : ''}${item.name ?? '下游'} ${share}${blocked ? ' · 饱和' : ''}`
        this.ensureLabel(nodeId, item.lon, item.lat, `<div class="trace-label is-downstream">${text}</div>`)
      }
    }
  }

  private sniffLabelHtml(node: TraceSniffIntersection, traceDirection: SniffTraceDirection): string {
    if (node.role === 'target') {
      return `<div class="trace-label"><div class="trace-name">${node.name ?? '目标路口'}</div><div class="trace-metric">目标</div></div>`
    }
    const cov = sniffCoverage(node)
    const label = cov != null ? `途经 ${cov.toFixed(1)}%` : node.is_topo_anchor ? '拓扑#1' : '拓扑'
    const cls = traceDirection === 'downstream' ? ' is-downstream' : ''
    const hop = node.in_main_corridor && node.corridor_hop ? `走廊#${node.corridor_hop} · ` : ''
    return `<div class="trace-label${cls}"><div class="trace-name">${node.name ?? '相邻路口'}</div><div class="trace-metric">${hop}${label}</div></div>`
  }

  /** 标准 link sniff 溯源：目标/主走廊/其他链分色，真实 link 双层发光，主链粒子与占比节点。 */
  renderSniffScene(scene: TraceSniffScene): void {
    const traceDirection = scene.trace_direction === 'downstream' ? 'downstream' : 'upstream'
    let topId = ''
    let topCoverage = -1
    const renderNodes = (scene.intersections ?? []).filter(shouldRenderSniffNode)
    renderNodes.forEach((node, index) => {
      const cov = sniffCoverage(node)
      const id = sniffNodeId(node, index)
      if (node.role !== 'target' && cov != null && cov > topCoverage) {
        topCoverage = cov
        topId = id
      }
    })

    renderNodes.forEach((node, index) => {
      const nodeId = sniffNodeId(node, index)
      for (const [linkIndex, link] of (node.links ?? []).entries()) {
        const path = sniffLinkPath(link)
        if (path.length < 2) continue
        this.revealSniffLink(`sniff:${nodeId}:${link.link_id ?? linkIndex}`, path, {
          node,
          traceDirection,
          linkRole: link.link_role,
        })
      }

      const center = node.center
      if (!center || center.length < 2) return
      const role =
        node.role === 'target' ? 'target' : traceDirection === 'downstream' ? 'downstream' : 'upstream'
      this.revealNode(nodeId, center[0], center[1], {
        role,
        coverage: sniffCoverage(node),
        clickable: true,
        onClick: () => this.toggleLabel(nodeId),
      })
      const defaultOpen =
        node.role === 'target' ||
        Boolean(node.in_main_corridor && sniffCoverage(node) != null) ||
        nodeId === topId ||
        Boolean(node.is_topo_anchor)
      this.ensureLabel(nodeId, center[0], center[1], this.sniffLabelHtml(node, traceDirection), defaultOpen)
    })
  }

  /** 目标路口脉冲节点（红）。 */
  revealTarget(id: string, lon: number, lat: number): void {
    this.revealNode(id, lon, lat, { role: 'target' })
  }

  /** 供 setFitView 收束整链。 */
  overlays(): Overlay[] {
    return this.fitList.filter(Boolean)
  }

  reset(): void {
    this.labelMarkers.clear()
    this.openLabelIds.clear()
    for (const list of this.byId.values()) {
      for (const overlay of list) overlay.setMap(null)
    }
    this.byId.clear()
    this.fitList.length = 0
  }

  dispose(): void {
    this.reset()
  }
}
