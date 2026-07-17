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
import {
  orientPathFromOrigin,
  pathPrefix,
  type LngLat,
} from './traceParticles'
import {
  MAP_PALETTE,
  TRACE_PALETTE as REFERENCE_TRACE_PALETTE,
} from './mapPalette'
import {
  buildSegmentCoverageLabelHtml,
  buildSegmentCoverageLinkHtml,
  buildSegmentCoverageTargetHtml,
} from './traceCoverageLabel'
import {
  buildUpstreamLabelHtml,
  coverageNodeStyle,
  formatTargetFlowShareLabel,
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
const EDGE_PALETTE = {
  upstream: { glow: MAP_PALETTE.primary, core: MAP_PALETTE.flow },
  downstream: { glow: MAP_PALETTE.success, core: MAP_PALETTE.success },
} as const

const SNIFF_PALETTE = REFERENCE_TRACE_PALETTE

export type TraceDirection = keyof typeof EDGE_PALETTE

const LABEL_OFFSET: [number, number] = [10, -48]
const DEFAULT_DETAIL_LABEL_LIMIT = 4

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
  turn_label?: string | null
  turn_dir_no?: number | null
  selected?: boolean | null
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
  private spreadAnimationId: number | null = null
  private spreadStartedAt = 0
  private spreadCompletion: Promise<void> = Promise.resolve()
  private resolveSpreadCompletion: (() => void) | null = null
  private spreadWaves: Array<{
    line: any
    path: LngLat[]
    delay: number
    duration: number
  }> = []

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
    const colors = EDGE_PALETTE[opts.traceKind ?? 'upstream']

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

  /**
   * 从目标点沿后端真实 link path 向上游逐条扩散。
   * 不创建动画 marker，避免把视觉粒子误读为新增流量点位；只让单色路径前缀增长一次。
   */
  private addSpreadWave(
    id: string,
    rawPath: LngLat[],
    origin: LngLat | null,
    order: number,
    total: number,
    trailColor: string = MAP_PALETTE.flow,
    trailWeight = 5,
  ): void {
    if (
      rawPath.length < 2 ||
      typeof window === 'undefined' ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) return
    const path = orientPathFromOrigin(rawPath, origin)
    if (path.length < 2) return
    const line = new this.AMap.Polyline({
      path: [path[0], path[0]],
      strokeColor: trailColor,
      strokeWeight: trailWeight,
      strokeOpacity: 0.88,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: 84,
    })
    this.register(`spread:${id}`, line)
    this.spreadWaves.push({
      line,
      path,
      delay: total <= 1 ? 0 : (Math.max(0, order) / (total - 1)) * 2200,
      duration: 1600,
    })
    this.startSpreadAnimation()
  }

  private startSpreadAnimation(): void {
    if (this.spreadAnimationId != null || !this.spreadWaves.length || typeof window === 'undefined') return
    this.spreadCompletion = new Promise<void>((resolve) => {
      this.resolveSpreadCompletion = resolve
    })
    this.spreadStartedAt = performance.now()
    const frame = (now: number) => {
      const elapsed = now - this.spreadStartedAt
      let pending = false
      for (const wave of this.spreadWaves) {
        const localMs = elapsed - wave.delay
        const progress = Math.max(0, Math.min(1, localMs / wave.duration))
        if (localMs < 0) {
          wave.line.setPath?.([wave.path[0], wave.path[0]])
          pending = true
        } else {
          wave.line.setPath?.(pathPrefix(wave.path, progress))
          if (progress < 1) pending = true
        }
      }
      if (pending && this.spreadWaves.length) {
        this.spreadAnimationId = window.requestAnimationFrame(frame)
      } else {
        this.spreadAnimationId = null
        this.resolveSpreadCompletion?.()
        this.resolveSpreadCompletion = null
      }
    }
    this.spreadAnimationId = window.requestAnimationFrame(frame)
  }

  private stopSpreadAnimation(): void {
    if (this.spreadAnimationId != null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(this.spreadAnimationId)
    }
    this.spreadAnimationId = null
    this.resolveSpreadCompletion?.()
    this.resolveSpreadCompletion = null
    this.spreadWaves = []
  }

  whenSpreadComplete(): Promise<void> {
    return this.spreadCompletion
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
      color?: string
      progressive?: boolean
    },
  ): void {
    if (this.byId.has(id) || path.length < 2) return
    const colors = opts.color
      ? { glow: opts.color, core: opts.color }
      : this.sniffColors(opts.node, opts.traceDirection)
    const isTarget = opts.node.role === 'target'
    const isMain = Boolean(opts.node.in_main_corridor)
    const entrance = isEntranceLink(opts.linkRole)
    const coverage = sniffCoverage(opts.node)
    const weight = isTarget ? (entrance ? 3 : 2.4) : upstreamEdgeStrokeWeight(coverage)
    const zBase = isTarget ? 62 : isMain ? 72 : 56

    const glow = new this.AMap.Polyline({
      path,
      strokeColor: colors.glow,
      strokeWeight: opts.color ? weight * 1.5 : isTarget ? weight * 2.2 : weight * 3,
      strokeOpacity: opts.color ? (opts.progressive ? 0.08 : 0.14) : isTarget ? 0.18 : 0.22,
      lineJoin: 'round',
      lineCap: opts.color ? 'butt' : 'round',
      zIndex: zBase,
    })
    const core = new this.AMap.Polyline({
      path,
      strokeColor: colors.core,
      strokeWeight: weight,
      strokeOpacity: opts.color && opts.traceDirection === 'upstream' && opts.progressive
        ? 0.2
        : isTarget ? (entrance ? 0.55 : 0.32) : 0.92,
      lineJoin: 'round',
      lineCap: 'butt',
      showDir: false,
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
    const rgb = role === 'downstream' ? '46,213,115' : '0,212,180'
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

  private bindLabelToggle(overlay: Overlay, nodeId: string): void {
    overlay.setOptions?.({ cursor: 'pointer' })
    overlay.on?.('click', () => this.toggleLabel(nodeId))
  }

  /** 稳定抽样，避免每次重放标签跳动，同时让标签沿整条链分散出现。 */
  private defaultLabelIndexes(total: number, limit = DEFAULT_DETAIL_LABEL_LIMIT): Set<number> {
    if (total <= limit) return new Set(Array.from({ length: total }, (_, i) => i))
    const indexes = new Set<number>()
    for (let i = 0; i < limit; i += 1) {
      indexes.add(Math.round((i * (total - 1)) / (limit - 1)))
    }
    return indexes
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

  /** 上游一跳来向：琥珀发光路径 + 占比缩放节点 + 点击展开/收起标签。 */
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
    const defaultLabels = this.defaultLabelIndexes(traces.length)

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
        this.ensureLabel(
          nodeId,
          item.upstream_lng,
          item.upstream_lat,
          label,
          i === topIdx || defaultLabels.has(i),
        )
      }
    })
  }

  /** 下游一跳去向：青蓝发光路径 + 节点 + 占比标签（无占比显示「拓扑」；饱和显示为治理绿）。 */
  renderDownstreamTraces(traces: DownstreamTraceItem[]): void {
    const byNode = new Map<string, DownstreamTraceItem[]>()
    traces.forEach((item, index) => {
      const path = (item.path ?? []).filter(Boolean) as LngLat[]
      const nodeId = String(item.downstream_inter_id ?? item.movement ?? path.length)
      if (path.length >= 2) {
        // 同一下游可能由多个目标转向到达；边 ID 必须包含转向，避免幂等注册吞掉关系。
        const relationId = `${item.turn_dir_no ?? item.turn_label ?? item.movement ?? 'turn'}:${nodeId}:${index}`
        this.revealEdge(`down:${relationId}`, path, {
          flowPct: item.share_pct ?? undefined,
          traceKind: 'downstream',
        })
      }
      byNode.set(nodeId, [...(byNode.get(nodeId) ?? []), item])
    })

    for (const [nodeId, items] of byNode) {
      const anchor = items.find((item) => item.selected) ?? items[0]
      if (anchor.lon != null && anchor.lat != null) {
        const blocked = items.some((item) => Boolean(item.capacity?.blocked))
        const coverage = items.reduce<number | null>((max, item) => {
          const value = item.share_pct
          return value != null && Number.isFinite(value) && (max == null || value > max) ? value : max
        }, null)
        this.revealNode(nodeId, anchor.lon, anchor.lat, {
          role: blocked ? 'governance' : 'downstream',
          coverage,
          clickable: true,
          onClick: () => this.toggleLabel(nodeId),
        })
        const details = items.map((item) => {
          const move = item.turn_label ?? turnLabelFromMovement(item.movement)
          const share = formatTargetFlowShareLabel(item.share_pct ?? null)
          return `${move ? `${move} ` : ''}${share}${item.capacity?.blocked ? ' · 饱和' : ''}`
        })
        const text = `${anchor.name ?? '下游'}<br>${details.join('<br>')}`
        this.ensureLabel(
          nodeId,
          anchor.lon,
          anchor.lat,
          `<div class="trace-label is-downstream">${text}</div>`,
          false,
        )
      }
    }
  }

  private sniffLabelHtml(node: TraceSniffIntersection, traceDirection: SniffTraceDirection): string {
    if (node.role === 'target') {
      return `<div class="trace-label"><div class="trace-name">${node.name ?? '目标路口'}</div><div class="trace-metric">目标</div></div>`
    }
    const cov = sniffCoverage(node)
    const label = formatTargetFlowShareLabel(cov)
    const cls = traceDirection === 'downstream' ? ' is-downstream' : ''
    return `<div class="trace-label${cls}"><div class="trace-name">${node.name ?? '相邻路口'}</div><div class="trace-metric">${label}</div></div>`
  }

  /**
   * 需求 33：按路段覆盖可视化（对齐 sequence_restore drawResult）。
   * 只消费后端真实 coords / lng,lat / ratio，禁止前端造几何。
   */
  renderSegmentCoverage(scene: {
    available?: boolean
    trace_direction?: string
    target?: {
      id?: string
      name?: string
      lng?: number | null
      lat?: number | null
      target_flow?: number | null
      [k: string]: unknown
    }
    intersections?: Array<{
      id?: string
      name?: string
      lng?: number | null
      lat?: number | null
      ratio?: number
      flow?: number
      fc?: number | null
      [k: string]: unknown
    }>
    links?: Array<{
      id?: string
      name?: string
      coords?: LngLat[]
      ratio?: number
      flow?: number
      [k: string]: unknown
    }>
    quality_filters?: { low_sample?: boolean }
    stats?: { target_flow?: number; low_sample?: boolean }
    visualization?: {
      particle_color?: string
      palette?: {
        severe?: string
        high?: string
        medium?: string
        low?: string
        near?: string
        middle?: string
        far?: string
      }
    }
  }, animate = true): void {
    if (!scene?.available) return
    const upstream = scene.trace_direction !== 'downstream'
    const nodeFill = upstream ? MAP_PALETTE.flow : MAP_PALETTE.reasoning
    const traceColor = scene.visualization?.particle_color ?? MAP_PALETTE.flow
    const targetFlow =
      scene.stats?.target_flow ??
      (typeof scene.target?.target_flow === 'number' ? scene.target.target_flow : null)
    const lowSample = Boolean(scene.quality_filters?.low_sample ?? scene.stats?.low_sample)

    const target = scene.target
    if (target && target.lng != null && target.lat != null) {
      const targetLabel = buildSegmentCoverageTargetHtml({
        name: String(target.name ?? '目标路口'),
        targetFlow,
        lowSample,
      })
      const marker = new this.AMap.Marker({
        position: [target.lng, target.lat],
        anchor: 'center',
        zIndex: 94,
        content: `<div class="trace-target-wrap"><div class="trace-node is-target"></div>${targetLabel}</div>`,
      })
      this.register('coverage:target', marker)
    }

    const eligibleLinks = (scene.links ?? [])
      .map((link, idx) => ({ link, idx }))
      .filter(({ link }) => {
        const path = (link.coords ?? []).filter(
          (p): p is LngLat => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]),
        )
        const ratio = typeof link.ratio === 'number' && Number.isFinite(link.ratio) ? link.ratio : 0
        return path.length >= 2 && ratio >= 0.05
      })
    const defaultLinkLabels = this.defaultLabelIndexes(eligibleLinks.length, 3)

    const spreadOrigin: LngLat | null =
      target && target.lng != null && target.lat != null ? [target.lng, target.lat] : null
    const spreadOrder = new Map<unknown, number>()
    ;[...eligibleLinks]
      .sort((a, b) => {
        const aOrder = Number((a.link as any).spread_order ?? (a.link as any).rank ?? a.idx)
        const bOrder = Number((b.link as any).spread_order ?? (b.link as any).rank ?? b.idx)
        return aOrder - bOrder
      })
      .forEach(({ link }, index) => spreadOrder.set(link, index))

    for (const { link, idx } of eligibleLinks) {
      const path = (link.coords ?? []).filter(
        (p): p is LngLat => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]),
      )
      const ratio = typeof link.ratio === 'number' && Number.isFinite(link.ratio) ? link.ratio : 0
      const weight = Math.max(3, Math.min(8, 2.5 + ratio * 18))
      const order = spreadOrder.get(link) ?? idx
      const line = new this.AMap.Polyline({
        path,
        strokeColor: traceColor,
        strokeOpacity: upstream && animate ? 0.2 : 0.82,
        strokeWeight: weight,
        lineJoin: 'round',
        lineCap: 'butt',
        showDir: false,
        zIndex: 72,
      })
      this.register(`coverage:link:${link.id ?? idx}`, line)
      if (upstream && animate) {
        this.addSpreadWave(
          String(link.id ?? idx),
          path,
          spreadOrigin,
          order,
          spreadOrder.size,
          traceColor,
          weight,
        )
      }
      const mid = path[Math.floor(path.length / 2)]
      if (mid) {
        this.ensureLabel(
          `coverage:link-label:${link.id ?? idx}`,
          mid[0],
          mid[1],
          buildSegmentCoverageLinkHtml({
            name: link.name ?? link.id ?? '路段',
            ratio,
            flow: link.flow,
            targetFlow,
          }),
          defaultLinkLabels.has(idx),
        )
      }
    }

    // 以当前镜头的屏幕像素做节点抽样；圆点本身也属于 marker，禁止互相覆盖。
    const markerPixels: Array<[number, number]> = []
    const intersections = [...(scene.intersections ?? [])]
      .filter((item) => item.lng != null && item.lat != null)
      .sort((a, b) => Number(b.ratio ?? 0) - Number(a.ratio ?? 0))
      .filter((item) => {
        if (item.lng == null || item.lat == null) return false
        const pixel = this.map.lngLatToContainer?.([item.lng, item.lat])
        const x = Number(pixel?.getX?.() ?? pixel?.x)
        const y = Number(pixel?.getY?.() ?? pixel?.y)
        if (!Number.isFinite(x) || !Number.isFinite(y)) return markerPixels.length < 14
        if (markerPixels.some(([px, py]) => Math.hypot(x - px, y - py) < 30)) return false
        markerPixels.push([x, y])
        return markerPixels.length <= 18
      })
    const defaultLabels = this.defaultLabelIndexes(intersections.length)
    for (const [idx, item] of intersections.entries()) {
      if (item.lng == null || item.lat == null) continue
      const ratio = typeof item.ratio === 'number' && Number.isFinite(item.ratio) ? item.ratio : 0
      const radius = Math.max(4, Math.min(9, 3.5 + ratio * 8))
      const marker = new this.AMap.CircleMarker({
        center: [item.lng, item.lat],
        radius,
        fillColor: nodeFill,
        fillOpacity: 0.78,
        strokeColor: '#ffffff',
        strokeWeight: 2,
        zIndex: 76,
      })
      const id = `coverage:inter:${item.id ?? idx}`
      this.register(id, marker)
      this.bindLabelToggle(marker, id)
      this.ensureLabel(
        id,
        item.lng,
        item.lat,
        buildSegmentCoverageLabelHtml({
          name: String(item.name ?? item.id ?? '来源路口'),
          ratio,
          flow: item.flow,
          targetFlow,
          kind: 'intersection',
        }),
        defaultLabels.has(idx),
      )
    }
  }

  /** 标准 link sniff 溯源：仅在 coverage 缺失时回退，仍只消费原有真实点位与 link。 */
  renderSniffScene(scene: TraceSniffScene, animate = true): void {
    const traceDirection = scene.trace_direction === 'downstream' ? 'downstream' : 'upstream'
    let topId = ''
    let topCoverage = -1
    const renderNodes = (scene.intersections ?? []).filter(shouldRenderSniffNode)
    const targetCenter = renderNodes.find((node) => node.role === 'target')?.center ?? null
    const spreadColor = scene.visualization?.particle_color ?? MAP_PALETTE.flow
    renderNodes.forEach((node, index) => {
      const cov = sniffCoverage(node)
      const id = sniffNodeId(node, index)
      if (node.role !== 'target' && cov != null && cov > topCoverage) {
        topCoverage = cov
        topId = id
      }
    })

    const defaultLabels = this.defaultLabelIndexes(renderNodes.length)
    renderNodes.forEach((node, index) => {
      const nodeId = sniffNodeId(node, index)
      for (const [linkIndex, link] of (node.links ?? []).entries()) {
        const path = sniffLinkPath(link)
        if (path.length < 2) continue
        this.revealSniffLink(`sniff:${nodeId}:${link.link_id ?? linkIndex}`, path, {
          node,
          traceDirection,
          linkRole: link.link_role,
          color: spreadColor,
          progressive: animate && traceDirection === 'upstream',
        })
        if (animate && traceDirection === 'upstream' && node.role !== 'target' && node.in_main_corridor) {
          this.addSpreadWave(
            `sniff:${nodeId}:${link.link_id ?? linkIndex}`,
            path,
            targetCenter as LngLat | null,
            index,
            renderNodes.length,
            spreadColor,
          )
        }
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
        node.role === 'target' || nodeId === topId || defaultLabels.has(index)
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
    this.stopSpreadAnimation()
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
