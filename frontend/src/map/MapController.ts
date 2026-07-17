import type { ActMapScene } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import { hasCoord, validPath } from '@/utils/guards'
import { ratio } from '@/utils/format'
import { buildMetricMarkers, markerHtml } from './mapMarkers'
import {
  clampZoomUp,
  drillToIntersection,
  fitBoundsForPoints,
  flyTo,
  bearingFromDirectionLabel,
  lerpPitch,
  microDollyToApproach,
  panToVisualCenter,
  samplePathForBounds,
  smoothPullback,
} from './amapUtils'
import {
  TraceLayer,
} from './traceLayer'
import { ChannelizationLayer } from './channelizationLayer'
import { DownstreamTopologyLayer, buildDownstreamTopology, resolvePrimaryDownstreamFocus } from './downstreamTopologyLayer'
import { sceneEvidencePolicy } from './sceneEvidencePolicy'
import { waitForMapBeat, waitForMapSubBeat } from '@/config/mapChoreography'
import { resolveRenderedLabelCollisions } from './labelLayout'
import { assertNoProductionMock } from './mapDataQuality'
import { MAP_PALETTE } from './mapPalette'
import { interpolatePath } from './traceParticles'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any

const JINAN_CENTER: [number, number] = [117.02, 36.66]
/** 渠化详情镜头（连贯下钻终点）与干线镜头（平滑抬升终点）。 */
const CHANNELIZATION_ZOOM = 18
const ARTERIAL_ZOOM = 17
const SAFE_PADDING: [number, number, number, number] = [72, 380, 100, 360]
/** 溯源幕给全景与侧栏留出更宽安全区，参考项目的城市级对象视角。 */
const TRACE_SAFE_PADDING: [number, number, number, number] = [96, 420, 142, 400]

function approxDistanceMeters(a: [number, number], b: [number, number]): number {
  const meanLat = ((a[1] + b[1]) * Math.PI) / 360
  const dx = (a[0] - b[0]) * 111_320 * Math.cos(meanLat)
  const dy = (a[1] - b[1]) * 110_540
  return Math.hypot(dx, dy)
}

export interface ApplySceneOptions {
  showMetrics?: boolean
  /** false 时仅补绘覆盖物、不重放镜头（流式同阶段数据补齐用，避免闪烁）。 */
  replayCamera?: boolean
}

/**
 * 地图控制器（纯 TS，包裹 AMap.Map 实例）。
 * 镜头连贯推进（单调下钻 + 平滑抬升）；覆盖物在镜头到位后绘制，避免闪现。
 * 用户手动拖拽/缩放后不再强制回拉视角（对齐 references/frontend-v2）。
 */
export class MapController {
  private AMap: AMapNS
  private map: AMapMap
  private overlays: any[] = []
  private traceLayer: TraceLayer | null = null
  private channelizationLayer: ChannelizationLayer | null = null
  private downstreamTopologyLayer: DownstreamTopologyLayer | null = null
  private currentZoom = 11
  private sceneToken = 0
  private userInteracted = false
  private programmatic = 0
  private programmaticUntil = 0
  private hiddenLabelCount = 0
  private particleAnimationId: number | null = null
  private animatedParticles: Array<{
    marker: any
    path: [number, number][]
    phase: number
    duration: number
  }> = []

  constructor(AMap: AMapNS, map: AMapMap) {
    this.AMap = AMap
    this.map = map
    this.currentZoom = map.getZoom?.() ?? 11
    // 用户手动操作后，后续系统步骤不再强拉视角
    map.on?.('dragend', () => {
      if (this.programmatic === 0 && Date.now() > this.programmaticUntil) this.userInteracted = true
    })
    map.on?.('zoomend', () => {
      this.currentZoom = map.getZoom?.() ?? this.currentZoom
      this.channelizationLayer?.applyLOD(this.currentZoom)
      if (this.programmatic === 0 && Date.now() > this.programmaticUntil) this.userInteracted = true
      this.scheduleLabelLayout()
    })
  }

  destroy() {
    this.clear()
  }

  /** 标记用户已手动干预（供外部 dragend/zoomend 兜底）。 */
  markUserInteracted() {
    this.userInteracted = true
  }

  /** 当前地图 zoom（供调试指示器读取）。 */
  getZoom(): number {
    return this.map.getZoom?.() ?? this.currentZoom
  }

  getHiddenLabelCount(): number {
    return this.hiddenLabelCount
  }

  private async withProgrammatic(fn: () => Promise<void> | void) {
    this.programmatic++
    // AMap 的 zoomend/moveend 可能晚于动画 Promise；保留尾窗，避免把系统镜头误判为人工干预。
    this.programmaticUntil = Date.now() + 6000
    try {
      await fn()
    } finally {
      this.programmatic--
      this.programmaticUntil = Date.now() + 900
    }
  }

  clear() {
    this.hiddenLabelCount = 0
    if (this.particleAnimationId != null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(this.particleAnimationId)
      this.particleAnimationId = null
    }
    this.animatedParticles = []
    if (this.overlays.length) {
      this.map.remove(this.overlays)
      this.overlays = []
    }
    if (this.traceLayer) {
      this.traceLayer.dispose()
      this.traceLayer = null
    }
    if (this.channelizationLayer) {
      this.channelizationLayer.dispose()
      this.channelizationLayer = null
    }
    if (this.downstreamTopologyLayer) {
      this.downstreamTopologyLayer.dispose()
      this.downstreamTopologyLayer = null
    }
  }

  private add(o: any) {
    this.overlays.push(o)
    this.map.add(o)
  }

  /** 应用某一阶段：连贯镜头 + 当前证据覆盖物。 */
  async applyScene(scene: ActMapScene, resp: RunResponse | null, opts: ApplySceneOptions = {}) {
    assertNoProductionMock(scene, resp)
    if (scene.camera === 'hold') {
      await waitForMapBeat(scene.evidence)
      return
    }
    const showMetrics = opts.showMetrics ?? false
    const replayCamera = opts.replayCamera ?? true
    const token = ++this.sceneToken
    const policy = sceneEvidencePolicy(scene, { showMetrics })
    this.clear()

    const ticket = resp?.diagnosis_ticket
    const target: [number, number] | null =
      ticket && hasCoord(ticket.lng, ticket.lat) ? [ticket.lng as number, ticket.lat as number] : null

    if (replayCamera && !this.userInteracted) {
      await this.withProgrammatic(() => this.moveCamera(scene, target, resp))
    }

    if (token !== this.sceneToken) return

    switch (scene.kind) {
      case 'intersection':
        if (target) this.drawIntersection(target, resp, false)
        break
      case 'lane':
        if (target) {
          this.drawIntersection(target, resp, policy.metricMarkers)
          if (policy.channelization) this.drawChannelization(resp, target)
        }
        break
      case 'trace':
      case 'corridor':
        if (policy.trace) this.drawTrace(resp, target, replayCamera)
        break
      case 'control':
        if (policy.trace) this.drawTrace(resp, target, replayCamera)
        if (policy.controlScope) this.drawControlScope(resp, target)
        break
    }

    // 单色溯源蔓延属于本幕地图动作；一次性走完后才释放 map barrier。
    if (scene.evidence === 'flow_trace') await this.traceLayer?.whenSpreadComplete()

    // 先呈现空间主体，再揭示关系、证据与结论标注，形成参考驾驶舱的分拍感。
    await waitForMapSubBeat(scene.evidence)
    if (token !== this.sceneToken) return

    if (policy.downstreamTopology) this.drawDownstreamTopology(resp, target)
    if (policy.metricMarkers && target) this.drawMetricMarkers(resp, target)
    if (policy.diagnosisCompare) this.drawDiagnosisCompare(resp)
    if (policy.causeAnnotation) this.drawCauseAnnotations(resp)
    if (policy.planPreview) this.drawPlanPreview(resp, target)
    await this.afterRender()
    if (token !== this.sceneToken) return
    await waitForMapBeat(scene.evidence)
  }

  private scheduleLabelLayout() {
    if (typeof window === 'undefined') return
    window.requestAnimationFrame(() => {
      const root = this.map.getContainer?.() as HTMLElement | undefined
      if (root) this.hiddenLabelCount = resolveRenderedLabelCollisions(root)
    })
  }

  private afterRender(): Promise<void> {
    if (typeof window === 'undefined') return Promise.resolve()
    return new Promise((resolve) => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        const root = this.map.getContainer?.() as HTMLElement | undefined
        if (root) {
          this.hiddenLabelCount = resolveRenderedLabelCollisions(root)
          root.querySelectorAll<HTMLElement>('.map-marker, .trace-label, .topology-label, .channel-label, .us-node, .us-badge').forEach((el, index) => {
            el.classList.remove('map-cinematic-reveal')
            el.style.animationDelay = `${Math.min(index, 8) * 70}ms`
            void el.offsetWidth
            el.classList.add('map-cinematic-reveal')
          })
        }
        resolve()
      }))
    })
  }

  /** 连贯运镜：城市→路口→车道 单调下钻；多节点 fitBounds；进口 micro-dolly。 */
  private async moveCamera(
    scene: ActMapScene,
    target: [number, number] | null,
    resp: RunResponse | null,
  ) {
    const stage = scene.evidence ?? scene.kind
    const pitchTarget = scene.pitch ?? 0
    try {
      const currentPitch = this.map.getPitch?.() ?? 0
      if (Math.abs(currentPitch - pitchTarget) > 5) {
        await lerpPitch(this.map, currentPitch, pitchTarget, stage === 'flow_trace' ? 900 : 550)
      } else {
        this.map.setPitch?.(pitchTarget)
      }
    } catch {
      /* ignore */
    }

    switch (scene.kind) {
      case 'city': {
        const z = scene.zoom ?? 11
        await flyTo(this.map, target ?? JINAN_CENTER, z, 900)
        this.currentZoom = z
        break
      }
      case 'intersection': {
        if (!target) break
        const z = clampZoomUp(this.currentZoom, scene.zoom ?? 16)
        await drillToIntersection(this.map, target, z)
        this.currentZoom = z
        break
      }
      case 'lane': {
        if (!target) break
        const requestedZoom = scene.zoom ?? CHANNELIZATION_ZOOM
        if (stage === 'plan_output') {
          await smoothPullback(this.map, target, requestedZoom, 1100)
          panToVisualCenter(this.map, target)
          this.currentZoom = requestedZoom
          break
        }
        const z = clampZoomUp(this.currentZoom, requestedZoom)
        if (stage === 'downstream_topology') {
          // 承接判别：先对准目标，再框住「本路口↔主要下游」，最后轻微落到下游图钉
          await drillToIntersection(this.map, target, Math.min(z, 17.5))
          this.currentZoom = this.map.getZoom?.() ?? Math.min(z, 17.5)
          const pts = this.collectDownstreamFocusPoints(resp, target)
          if (pts.length >= 2) {
            await fitBoundsForPoints(this.map, pts, {
              maxZoom: 17.4,
              duration: 950,
              padding: SAFE_PADDING,
              AMap: this.AMap,
            })
            this.currentZoom = this.map.getZoom?.() ?? this.currentZoom
          }
          break
        }
        // 案例校验等：从溯源 15.5 丝滑下钻回车道级
        if (this.currentZoom + 0.3 < z) {
          await drillToIntersection(this.map, target, z)
        } else {
          await flyTo(this.map, target, z, 900)
          panToVisualCenter(this.map, target)
        }
        this.currentZoom = z
        const bearing = bearingFromDirectionLabel(resp?.diagnosis_ticket?.direction)
        if (bearing != null && (stage === 'overflow_validation' || stage === 'cause_annotation')) {
          this.currentZoom = await microDollyToApproach(this.map, target, bearing, this.currentZoom)
        }
        break
      }
      case 'trace':
      case 'corridor': {
        if (!target) break
        const isFlowTrace = stage === 'flow_trace'
        if (isFlowTrace) {
          // 对真实溯源点 fitBounds，长走廊不再用固定 zoom 截断端点。
          const tracePts = this.collectTraceBoundsPoints(resp, target)
          await fitBoundsForPoints(this.map, tracePts, {
            maxZoom: Math.min(scene.zoom ?? 13.8, 13.8),
            padding: TRACE_SAFE_PADDING,
            duration: 1500,
            AMap: this.AMap,
          })
          this.currentZoom = this.map.getZoom?.() ?? this.currentZoom
          break
        }
        const tracePts = this.collectTraceBoundsPoints(resp, target)
        if (tracePts.length >= 2) {
          await fitBoundsForPoints(this.map, tracePts, {
            maxZoom: scene.zoom ?? ARTERIAL_ZOOM,
            padding: SAFE_PADDING,
            duration: 1000,
            AMap: this.AMap,
          })
          this.currentZoom = this.map.getZoom?.() ?? this.currentZoom
        } else {
          const z = Math.max(scene.zoom ?? ARTERIAL_ZOOM, ARTERIAL_ZOOM)
          const dur = Math.abs(this.currentZoom - z) > 1 ? 1100 : 850
          await smoothPullback(this.map, target, z, dur)
          panToVisualCenter(this.map, target)
          this.currentZoom = z
        }
        break
      }
      case 'control': {
        if (!target) break
        const ctrlPts = this.collectControlScopePoints(resp, target)
        if (ctrlPts.length >= 2) {
          await fitBoundsForPoints(this.map, ctrlPts, { maxZoom: 17.5, duration: 900, padding: SAFE_PADDING, AMap: this.AMap })
          this.currentZoom = this.map.getZoom?.() ?? this.currentZoom
        } else {
          const z = clampZoomUp(this.currentZoom, scene.zoom ?? CHANNELIZATION_ZOOM)
          await drillToIntersection(this.map, target, z)
          this.currentZoom = z
        }
        break
      }
    }
  }

  private collectDiagnosisComparePoints(resp: RunResponse | null): [number, number][] {
    const pts: [number, number][] = []
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.diagnosis_compare
    for (const node of [scene?.target, scene?.downstream]) {
      if (node && hasCoord(node.lng, node.lat)) pts.push([node.lng, node.lat])
    }
    const primary = resolvePrimaryDownstreamFocus(resp)
    if (primary) pts.push(primary.position)
    return pts
  }

  /** 承接判别框选点：diagnosis_compare + 主要下游锚点。 */
  private collectDownstreamFocusPoints(
    resp: RunResponse | null,
    target: [number, number] | null,
  ): [number, number][] {
    const pts = this.collectDiagnosisComparePoints(resp)
    if (target) pts.unshift(target)
    const primary = resolvePrimaryDownstreamFocus(resp)
    if (primary) pts.push(primary.position)
    const uniq: [number, number][] = []
    for (const p of pts) {
      if (!uniq.some((q) => Math.abs(q[0] - p[0]) < 1e-8 && Math.abs(q[1] - p[1]) < 1e-8)) uniq.push(p)
    }
    return uniq
  }

  private collectTraceBoundsPoints(resp: RunResponse | null, target: [number, number]): [number, number][] {
    const pts: [number, number][] = [target]
    const scenes = resp?.phases?.diagnosis?.map_scenes ?? {}
    const coverage = (scenes as any).flow_trace_segment_coverage_map
    if (coverage?.available) {
      // 3D 源码只框选目标 2km 上游拓扑；远端真实证据仍渲染，但不把镜头拉成全市缩略图。
      const radius = Number(coverage.visualization?.camera?.radius_m ?? 2000)
      const inCameraRadius = (point: [number, number]) => approxDistanceMeters(point, target) <= radius
      const t = coverage.target
      if (t && hasCoord(t.lng, t.lat)) pts.push([t.lng, t.lat])
      for (const inter of coverage.intersections ?? []) {
        if (hasCoord(inter?.lng, inter?.lat)) {
          const point: [number, number] = [inter.lng, inter.lat]
          if (inCameraRadius(point)) pts.push(point)
        }
      }
      for (const link of coverage.links ?? []) {
        for (const pt of samplePathForBounds(validPath(link?.coords), 6)) {
          if (inCameraRadius(pt)) pts.push(pt)
        }
      }
      return pts
    }
    const sniff = (scenes as any).flow_trace_links_sniff_map
    for (const inter of sniff?.intersections ?? []) {
      const c = inter?.center
      if (Array.isArray(c) && c.length >= 2 && hasCoord(c[0], c[1])) pts.push([c[0], c[1]])
      for (const link of inter?.links ?? []) {
        for (const pt of samplePathForBounds(validPath(link?.path ?? link?.coords), 5)) pts.push(pt)
      }
    }
    for (const t of resp?.phases?.diagnosis?.flow_trace?.entry_traces ?? []) {
      if (hasCoord(t.upstream_lng, t.upstream_lat)) pts.push([t.upstream_lng as number, t.upstream_lat as number])
      for (const pt of samplePathForBounds(validPath(t.path), 4)) pts.push(pt)
    }
    for (const t of (scenes as any).downstream_trace_map?.turn_traces ?? []) {
      if (hasCoord(t.lon, t.lat)) pts.push([t.lon, t.lat])
      for (const pt of samplePathForBounds(validPath(t.path), 4)) pts.push(pt)
    }
    return pts
  }

  private collectControlScopePoints(resp: RunResponse | null, target: [number, number]): [number, number][] {
    const csm = resp?.phases?.strategy?.control_scope_map
    const pts: [number, number][] = [target]
    const center = csm?.center
    if (Array.isArray(center) && hasCoord(center[0], center[1])) pts.push(center as [number, number])
    for (const p of csm?.upstream_metering_points ?? []) {
      if (hasCoord((p as any).lng, (p as any).lat)) pts.push([(p as any).lng, (p as any).lat])
    }
    for (const p of csm?.downstream_protection_nodes ?? []) {
      if (hasCoord((p as any).lng, (p as any).lat)) pts.push([(p as any).lng, (p as any).lat])
    }
    for (const edge of (csm as any)?.coordination_paths ?? []) {
      for (const pt of validPath(edge.path)) pts.push(pt)
    }
    return pts
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

  /** 目标标记 + 后端真实 highlight_path；禁止用经纬度偏移合成路口框。 */
  private drawIntersection(center: [number, number], resp: RunResponse | null, overflow = false) {
    // 仅保留目标脉冲点；上下游路口名改由拓扑卡片呈现，避免黄色文字 marker 与卡片重叠冗余
    const focusColor = overflow ? MAP_PALETTE.danger : MAP_PALETTE.primary
    this.drawFocusRings(center, focusColor)
    this.add(this.pulseDot(center, focusColor))

    const path = validPath(resp?.phases?.intent?.spatial_scene?.highlight_path)
    if (path.length >= 2) {
      this.add(
        new this.AMap.Polyline({
          path,
          strokeColor: MAP_PALETTE.primary,
          strokeWeight: 14,
          strokeOpacity: 0.16,
          lineCap: 'round',
          zIndex: 54,
        }),
      )
      this.addFlowParticles(path, MAP_PALETTE.primary, 3, 2100)
      this.add(
        new this.AMap.Polyline({
          path,
          strokeColor: MAP_PALETTE.primary,
          strokeWeight: 6,
          strokeOpacity: 0.95,
          showDir: true,
          lineCap: 'round',
          zIndex: 56,
        }),
      )
    }
    if (overflow) this.drawQueueEvidence(resp)
  }

  private drawQueueEvidence(resp: RunResponse | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.queue_evidence
    const path = validPath(scene?.path)
    if (path.length < 2) return
    this.add(new this.AMap.Polyline({
      path,
      strokeColor: MAP_PALETTE.danger,
      strokeWeight: 22,
      strokeOpacity: 0.14,
      lineCap: 'round',
      zIndex: 68,
    }))
    this.add(new this.AMap.Polyline({
      path,
      strokeColor: MAP_PALETTE.danger,
      strokeWeight: 12,
      strokeOpacity: 0.58,
      lineCap: 'round',
      zIndex: 70,
    }))
    this.addFlowParticles(path, MAP_PALETTE.danger, 4, 1900)
    const anchor = Array.isArray(scene?.label_anchor) && hasCoord(scene.label_anchor[0], scene.label_anchor[1])
      ? scene.label_anchor as [number, number]
      : null
    if (anchor) {
      this.add(new this.AMap.Marker({
        position: anchor,
        content: markerHtml({ position: anchor, kind: 'alert', title: '排队/库容', value: `${Math.round(scene.queue_length_m ?? 0)}m / ${Math.round(scene.storage_length_m ?? 0)}m`, severity: 'high' }),
        offset: new this.AMap.Pixel(0, -34),
        anchor: 'center',
      }))
    }
    const stopLine = validPath(scene?.stop_line?.geometry)
    if (stopLine.length >= 2) {
      this.add(new this.AMap.Polyline({ path: stopLine, strokeColor: '#ffffff', strokeWeight: 5, strokeOpacity: 0.9, zIndex: 76 }))
    }
  }

  /** 溯源阶段：优先路段覆盖；缺失时回退到后端真实 link sniff 场景。 */
  private drawTrace(resp: RunResponse | null, target: [number, number] | null, animate = true) {
    this.traceLayer = new TraceLayer(this.AMap, this.map)

    const scenes = resp?.phases?.diagnosis?.map_scenes ?? {}
    const coverage = (scenes as any).flow_trace_segment_coverage_map
    const sniff = (scenes as any).flow_trace_links_sniff_map
    if (coverage?.available) {
      // 恢复原始选择逻辑：coverage 存在时只呈现 coverage 的点位/路段，禁止叠加 sniff 路网。
      this.traceLayer.renderSegmentCoverage(coverage, animate)
      return
    }

    if (sniff?.available) {
      this.traceLayer.renderSniffScene(sniff, animate)
      return
    }

    if (target) this.traceLayer.revealTarget('target', target[0], target[1])

    if (target) {
      this.add(
        new this.AMap.Text({
          text: '<div class="trace-label"><div class="trace-name">暂无路段覆盖溯源数据</div></div>',
          position: target,
          offset: new this.AMap.Pixel(12, -28),
          zIndex: 30,
        }),
      )
    }
  }

  /** zoom18 渠化：严格消费后端 channelization_map 的真实 link geometry/lane_info/指标。 */
  private drawChannelization(resp: RunResponse | null, target: [number, number] | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.channelization_map
    if (!scene?.available || !target) return
    this.channelizationLayer = new ChannelizationLayer(this.AMap, this.map, {
      ...scene,
      center: (scene.center ?? target) as [number, number],
    })
    this.channelizationLayer.render()
    const ticket = resp?.diagnosis_ticket
    this.channelizationLayer.highlightApproach(ticket?.direction, ticket?.movement)
  }

  /** 目标路口一跳下游十字拓扑：所有真实出口 link + 左/直/右关系与承接指标。 */
  private drawDownstreamTopology(resp: RunResponse | null, target: [number, number] | null) {
    const scenes = (resp?.phases?.diagnosis?.map_scenes ?? {}) as Record<string, any>
    const primary = resolvePrimaryDownstreamFocus(resp)
    const topology = buildDownstreamTopology(scenes, target, {
      primaryId: primary?.id,
      primaryFocus: primary,
    })
    if (!topology.nodes.length && !topology.edges.length) return
    this.downstreamTopologyLayer = new DownstreamTopologyLayer(this.AMap, this.map)
    this.downstreamTopologyLayer.render(topology)
  }

  private drawControlScope(resp: RunResponse | null, target: [number, number] | null) {
    const csm = resp?.phases?.strategy?.control_scope_map
    const center = csm?.center && hasCoord(csm.center[0], csm.center[1]) ? (csm.center as [number, number]) : target
    if (center) {
      this.add(
        new this.AMap.Marker({
          position: center,
          content: markerHtml({
            position: center,
            kind: 'metric',
            title: '目标路口',
            value: '小步释放',
            severity: 'low',
          }),
          offset: new this.AMap.Pixel(-40, -28),
          anchor: 'center',
        }),
      )
    }
    for (const p of csm?.upstream_metering_points ?? []) {
      const lng = (p as any).lng
      const lat = (p as any).lat
      if (hasCoord(lng, lat)) {
        const pos: [number, number] = [lng, lat]
        this.add(
          new this.AMap.Marker({
            position: pos,
            content: markerHtml({
              position: pos,
              kind: 'alert',
              title: '控流闸口',
              value: (p as any).label ?? '上游控流',
              severity: 'high',
            }),
            offset: new this.AMap.Pixel(-40, -28),
            anchor: 'center',
          }),
        )
      }
    }
    for (const p of csm?.downstream_protection_nodes ?? []) {
      const lng = (p as any).lng
      const lat = (p as any).lat
      if (hasCoord(lng, lat)) {
        // 策略阶段：只保留保护节点定位点，不再叠黄色「保护节点」文字卡片
        this.add(this.pulseDot([lng, lat], MAP_PALETTE.warning))
      }
    }
    for (const edge of (csm as any)?.coordination_paths ?? []) {
      const path = validPath(edge.path)
      if (path.length >= 2) {
        this.add(
          new this.AMap.Polyline({
            path,
            strokeColor: MAP_PALETTE.warning,
            strokeWeight: 2,
            strokeOpacity: 0.25,
            strokeStyle: 'solid',
            showDir: true,
            zIndex: 60,
          }),
        )
        this.addFlowParticles(path, MAP_PALETTE.warning, 1, 2600)
        this.add(
          new this.AMap.Polyline({
            path,
            strokeColor: MAP_PALETTE.warning,
            strokeWeight: 5,
            strokeOpacity: 0.82,
            strokeStyle: 'dashed',
            showDir: true,
            zIndex: 62,
          }),
        )
      }
    }
    const riskPolygon = validPath((csm as any)?.risk_boundary?.geometry?.polygon)
    if (riskPolygon.length >= 3) {
      this.add(new this.AMap.Polygon({
        path: riskPolygon,
        strokeColor: MAP_PALETTE.flow,
        strokeWeight: 2,
        strokeStyle: 'dashed',
        fillColor: MAP_PALETTE.primary,
        fillOpacity: 0.09,
        zIndex: 35,
      }))
    }
  }

  /** act3–4：本路口 vs 主要下游双节点对比（callout + 连线）。 */
  private drawDiagnosisCompare(resp: RunResponse | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.diagnosis_compare
    if (!scene?.available) return
    const nodes = [scene.target, scene.downstream].filter(Boolean)
    const positions: [number, number][] = []
    for (const node of nodes) {
      if (!node || !hasCoord(node.lng, node.lat)) continue
      const pos: [number, number] = [node.lng, node.lat]
      positions.push(pos)
      const color = node.role === 'target' ? MAP_PALETTE.danger : MAP_PALETTE.flow
      const metrics = node.metrics ?? {}
      const title = node.role === 'target' ? '本路口' : '主要下游'
      const value =
        node.role === 'target'
          ? `排队 ${ratio(metrics.queue_ratio)}`
          : `饱和 ${ratio(metrics.saturation)}`
      this.add(
        new this.AMap.Marker({
          position: pos,
          content: markerHtml({
            position: pos,
            kind: node.role === 'target' ? 'alert' : 'metric',
            title,
            value,
            subtitle: node.inter_name ?? '',
            severity: node.role === 'target' ? 'high' : 'medium',
          }),
          offset: new this.AMap.Pixel(-40, -32),
          anchor: 'center',
        }),
      )
      this.add(this.pulseDot(pos, color))
    }
    if (positions.length >= 2) {
      this.add(
        new this.AMap.Polyline({
          path: positions,
          strokeColor: MAP_PALETTE.warning,
          strokeWeight: 3,
          strokeOpacity: 0.65,
          strokeStyle: 'dashed',
          showDir: true,
        }),
      )
    }
  }

  /** act6：主因关联空间对象（进口/下游）；相似案例仅在右侧面板呈现，不在地图堆叠。 */
  private drawCauseAnnotations(resp: RunResponse | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.cause_spatial
    if (!scene?.available) return
    const reduced =
      typeof window !== 'undefined' &&
      !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    for (const ann of scene.annotations ?? []) {
      if (!hasCoord(ann.lng, ann.lat)) continue
      if (ann.kind === 'case_ref') continue
      const color = ann.color ?? MAP_PALETTE.primary
      const pos: [number, number] = [ann.lng as number, ann.lat as number]
      // 案例校验：下游不再叠黄色文字卡片，只保留问题进口卡片 + 下游连线
      if (ann.kind === 'downstream') {
        const downstreamColor = MAP_PALETTE.flow
        this.drawFocusRings(pos, downstreamColor)
        this.add(this.pulseDot(pos, downstreamColor))
      } else {
        const label = ann.label ?? ann.case_id ?? '标注'
        this.add(
          new this.AMap.Marker({
            position: pos,
            content: markerHtml({
              position: pos,
              kind: 'metric',
              title: ann.kind === 'approach' ? '问题进口' : '标注',
              value: label,
              severity: ann.kind === 'approach' ? 'high' : 'medium',
            }),
            offset: new this.AMap.Pixel(-36, -28),
            anchor: 'center',
          }),
        )
      }
      if (!reduced && ann.kind === 'downstream' && ann.inter_id) {
        const target = resp?.diagnosis_ticket
        if (target && hasCoord(target.lng, target.lat)) {
          this.add(
            new this.AMap.Polyline({
              path: [
                [target.lng as number, target.lat as number],
                pos,
              ],
              strokeColor: color,
              strokeWeight: 3,
              strokeOpacity: 0.55,
              strokeStyle: 'dotted',
            }),
          )
        }
      }
    }
  }

  /** act8：配时变化预览标签（静态，无动画）。 */
  private drawPlanPreview(resp: RunResponse | null, target: [number, number] | null) {
    const scene = (resp?.plan as any)?.map_scene ?? (resp?.phases?.diagnosis?.map_scenes as any)?.plan_preview
    if (!scene?.available) return
    const center = scene.center && hasCoord(scene.center[0], scene.center[1]) ? scene.center : target
    if (!center) return
    const changes = scene.phase_changes ?? []
    const summary = changes
      .slice(0, 2)
      .map((c: any) => `${c.phase_stage_name ?? c.label}:${c.green_delta_s > 0 ? '+' : ''}${c.green_delta_s}s`)
      .join(' ')
    const label = summary || scene.plan_name || '配时预览'
    for (const change of changes) {
      const paths = [change?.path, ...(Array.isArray(change?.paths) ? change.paths : [])]
      for (const rawPath of paths) {
        const path = validPath(rawPath)
        if (path.length >= 2) {
          const color = change.green_delta_s > 0 ? MAP_PALETTE.success : MAP_PALETTE.warning
          this.add(new this.AMap.Polyline({ path, strokeColor: color, strokeWeight: 20, strokeOpacity: 0.14, lineCap: 'round', zIndex: 78 }))
          this.add(new this.AMap.Polyline({ path, strokeColor: color, strokeWeight: 8, strokeOpacity: 0.86, showDir: true, lineCap: 'round', zIndex: 80 }))
          this.addFlowParticles(path, color, 2, 2300)
        }
      }
    }
    this.add(this.pulseMarker(center as [number, number], MAP_PALETTE.success, label))
    if (scene.cycle_delta_s != null) {
      this.add(
        new this.AMap.Marker({
          position: center,
          content: `<div class="us-badge" style="margin-top:28px;color:#2ed573;font-size:10px">周期${scene.cycle_delta_s > 0 ? '+' : ''}${scene.cycle_delta_s}s</div>`,
          offset: new this.AMap.Pixel(-20, 0),
          anchor: 'top-center',
        }),
      )
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

  /** 参考城市驾驶舱的双环焦点：内环锁定对象，外环表达当前 act 的关注范围。 */
  private drawFocusRings(pos: [number, number], color: string) {
    if (typeof this.AMap.CircleMarker !== 'function') return
    this.add(new this.AMap.CircleMarker({
      center: pos,
      radius: 24,
      strokeColor: color,
      strokeWeight: 2,
      strokeOpacity: 0.68,
      fillOpacity: 0,
      zIndex: 50,
    }))
    this.add(new this.AMap.CircleMarker({
      center: pos,
      radius: 12,
      strokeColor: '#ffffff',
      strokeWeight: 2,
      strokeOpacity: 0.9,
      fillColor: color,
      fillOpacity: 0.14,
      zIndex: 51,
    }))
  }

  /** 用真实路线几何驱动流光粒子；减少动态偏好下自动禁用。 */
  private addFlowParticles(path: [number, number][], color: string, count: number, duration: number) {
    if (
      path.length < 2 ||
      typeof window === 'undefined' ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) return
    for (let i = 0; i < count; i++) {
      const marker = new this.AMap.Marker({
        position: path[0],
        content: `<div class="map-flow-particle" style="--c:${color}"></div>`,
        // 参考项目使用 anchor:center；禁止再叠加像素 offset，否则粒子会偏离 path。
        anchor: 'center',
        clickable: false,
        zIndex: 92,
      })
      this.add(marker)
      this.animatedParticles.push({ marker, path, phase: i / count, duration })
    }
    this.startParticleAnimation()
  }

  private startParticleAnimation() {
    if (this.particleAnimationId != null || typeof window === 'undefined') return
    const startedAt = performance.now()
    const frame = (now: number) => {
      for (const particle of this.animatedParticles) {
        const t = ((now - startedAt) / particle.duration + particle.phase) % 1
        particle.marker.setPosition?.(lerpPath(particle.path, t))
      }
      if (this.animatedParticles.length) {
        this.particleAnimationId = window.requestAnimationFrame(frame)
      } else {
        this.particleAnimationId = null
      }
    }
    this.particleAnimationId = window.requestAnimationFrame(frame)
  }

  /** 无文字脉冲点，避免与路口卡片重复堆叠路口名。 */
  private pulseDot(pos: [number, number], color: string) {
    return new this.AMap.Marker({
      position: pos,
      content: `<div class="us-pulse-dot" style="--c:${color}"></div>`,
      offset: new this.AMap.Pixel(-7, -7),
      clickable: false,
    })
  }

  resetToCity() {
    this.clear()
    this.currentZoom = 11
    this.userInteracted = false
    this.programmaticUntil = Date.now() + 1600
    try {
      this.map.setPitch?.(20)
    } catch {
      /* ignore */
    }
    return flyTo(this.map, JINAN_CENTER, 11, 900)
  }
}

/** 沿折线按 t∈[0,1] 线性插值（纯函数，供测试；委托 traceParticles.interpolatePath）。 */
export function lerpPath(path: [number, number][], t: number): [number, number] {
  return interpolatePath(path, t) ?? [0, 0]
}
