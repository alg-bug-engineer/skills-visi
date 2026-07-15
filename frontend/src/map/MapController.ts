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

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any

const JINAN_CENTER: [number, number] = [117.02, 36.66]
/** 渠化详情镜头（连贯下钻终点）与干线镜头（平滑抬升终点）。 */
const CHANNELIZATION_ZOOM = 18
const ARTERIAL_ZOOM = 17
/** 流量溯源走廊视角：固定路口中心上拉，展开上下游全貌。 */
const FLOW_TRACE_ZOOM = 15.5

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

  constructor(AMap: AMapNS, map: AMapMap) {
    this.AMap = AMap
    this.map = map
    this.currentZoom = map.getZoom?.() ?? 11
    // 用户手动操作后，后续系统步骤不再强拉视角
    map.on?.('dragend', () => {
      this.userInteracted = true
    })
    map.on?.('zoomend', () => {
      this.currentZoom = map.getZoom?.() ?? this.currentZoom
      this.channelizationLayer?.applyLOD(this.currentZoom)
      if (this.programmatic === 0) this.userInteracted = true
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

  private async withProgrammatic(fn: () => Promise<void> | void) {
    this.programmatic++
    try {
      await fn()
    } finally {
      this.programmatic--
    }
  }

  clear() {
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
        if (policy.trace) this.drawTrace(resp, target)
        break
      case 'control':
        if (policy.trace) this.drawTrace(resp, target)
        if (policy.controlScope) this.drawControlScope(resp, target)
        break
    }

    if (policy.downstreamTopology) this.drawDownstreamTopology(resp, target)
    if (policy.metricMarkers && target) this.drawMetricMarkers(resp, target)
    if (policy.diagnosisCompare) this.drawDiagnosisCompare(resp)
    if (policy.causeAnnotation) this.drawCauseAnnotations(resp)
    if (policy.planPreview) this.drawPlanPreview(resp, target)
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
        await lerpPitch(this.map, currentPitch, pitchTarget, 550)
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
        const z = clampZoomUp(this.currentZoom, scene.zoom ?? CHANNELIZATION_ZOOM)
        if (stage === 'downstream_topology') {
          // 承接判别：先对准目标，再框住「本路口↔主要下游」，最后轻微落到下游图钉
          await drillToIntersection(this.map, target, Math.min(z, 17.5))
          this.currentZoom = this.map.getZoom?.() ?? Math.min(z, 17.5)
          const primary = resolvePrimaryDownstreamFocus(resp)
          const pts = this.collectDownstreamFocusPoints(resp, target)
          if (pts.length >= 2) {
            await fitBoundsForPoints(this.map, pts, {
              maxZoom: 17.4,
              duration: 950,
              padding: [110, 120, 140, 120],
              AMap: this.AMap,
            })
            this.currentZoom = this.map.getZoom?.() ?? this.currentZoom
          }
          if (primary) {
            const focusZoom = Math.min(17.2, Math.max(16.2, this.currentZoom))
            await flyTo(this.map, primary.position, focusZoom, 750)
            panToVisualCenter(this.map, primary.position)
            this.currentZoom = focusZoom
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
          // 镜头中心保持目标路口，只丝滑上拉到 15.5，展示溯源全貌
          const z = FLOW_TRACE_ZOOM
          const dur = Math.abs(this.currentZoom - z) > 0.8 ? 1300 : 1000
          await smoothPullback(this.map, target, z, dur)
          panToVisualCenter(this.map, target)
          this.currentZoom = z
          break
        }
        const tracePts = this.collectTraceBoundsPoints(resp, target)
        if (tracePts.length >= 2) {
          await fitBoundsForPoints(this.map, tracePts, {
            maxZoom: scene.zoom ?? ARTERIAL_ZOOM,
            padding: [80, 80, 80, 80],
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
          await fitBoundsForPoints(this.map, ctrlPts, { maxZoom: 17.5, duration: 900, AMap: this.AMap })
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
      const t = coverage.target
      if (t && hasCoord(t.lng, t.lat)) pts.push([t.lng, t.lat])
      for (const inter of coverage.intersections ?? []) {
        if (hasCoord(inter?.lng, inter?.lat)) pts.push([inter.lng, inter.lat])
      }
      for (const link of coverage.links ?? []) {
        for (const pt of samplePathForBounds(validPath(link?.coords), 6)) pts.push(pt)
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
    // 仅保留目标脉冲点；上下游路口名改由拓扑卡片呈现，避免黄色文字 marker 与卡片重叠冗余
    this.add(this.pulseDot(center, overflow ? '#ff5050' : '#00e5ff'))

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
  }

  /** 溯源阶段：优先路段覆盖；缺失时回退到后端真实 link sniff 场景。 */
  private drawTrace(resp: RunResponse | null, target: [number, number] | null) {
    this.traceLayer = new TraceLayer(this.AMap, this.map)

    const scenes = resp?.phases?.diagnosis?.map_scenes ?? {}
    const coverage = (scenes as any).flow_trace_segment_coverage_map
    if (coverage?.available) {
      this.traceLayer.renderSegmentCoverage(coverage)
      return
    }

    const sniff = (scenes as any).flow_trace_links_sniff_map
    if (sniff?.available) {
      this.traceLayer.renderSniffScene(sniff)
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
        this.add(this.pulseDot([lng, lat], '#f5a623'))
      }
    }
    for (const edge of (csm as any)?.coordination_paths ?? []) {
      const path = validPath(edge.path)
      if (path.length >= 2) {
        this.add(
          new this.AMap.Polyline({
            path,
            strokeColor: '#f5a623',
            strokeWeight: 2,
            strokeOpacity: 0.25,
            strokeStyle: 'solid',
            showDir: true,
            zIndex: 60,
          }),
        )
        this.add(
          new this.AMap.Polyline({
            path,
            strokeColor: '#ffcf7a',
            strokeWeight: 5,
            strokeOpacity: 0.82,
            strokeStyle: 'dashed',
            showDir: true,
            zIndex: 62,
          }),
        )
      }
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
      const color = node.role === 'target' ? '#ff5050' : '#38bdf8'
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
          strokeColor: '#f5a623',
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
      const color = ann.color ?? '#00e5ff'
      const pos: [number, number] = [ann.lng as number, ann.lat as number]
      // 案例校验：下游不再叠黄色文字卡片，只保留问题进口卡片 + 下游连线
      if (ann.kind === 'downstream') {
        this.add(this.pulseDot(pos, color === '#f5a623' ? '#38bdf8' : color))
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
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.plan_preview
    if (!scene?.available) return
    const center = scene.center && hasCoord(scene.center[0], scene.center[1]) ? scene.center : target
    if (!center) return
    const changes = scene.phase_changes ?? []
    const summary = changes
      .slice(0, 2)
      .map((c: any) => `${c.phase_stage_name ?? c.label}:${c.green_delta_s > 0 ? '+' : ''}${c.green_delta_s}s`)
      .join(' ')
    const label = summary || scene.plan_name || '配时预览'
    this.add(this.pulseMarker(center as [number, number], '#6dffb5', label))
    if (scene.cycle_delta_s != null) {
      this.add(
        new this.AMap.Marker({
          position: center,
          content: `<div class="us-badge" style="margin-top:28px;color:#6dffb5;font-size:10px">周期${scene.cycle_delta_s > 0 ? '+' : ''}${scene.cycle_delta_s}s</div>`,
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
