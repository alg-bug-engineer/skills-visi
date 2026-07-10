import type { ActMapScene } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'
import { hasCoord, validPath } from '@/utils/guards'
import { buildMetricMarkers, markerHtml } from './mapMarkers'
import {
  clampZoomUp,
  drillToIntersection,
  flyTo,
  panToVisualCenter,
  smoothPullback,
} from './amapUtils'
import {
  TraceLayer,
  type DownstreamTraceItem,
  type UpstreamTraceItem,
} from './traceLayer'
import { buildLegacySniffScene, type TraceSniffScene } from './traceSniff'
import { ChannelizationLayer } from './channelizationLayer'
import { DownstreamTopologyLayer, buildDownstreamTopology } from './downstreamTopologyLayer'
import { sceneEvidencePolicy } from './sceneEvidencePolicy'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any

const JINAN_CENTER: [number, number] = [117.02, 36.66]
/** 渠化详情镜头（连贯下钻终点）与干线镜头（平滑抬升终点）。 */
const CHANNELIZATION_ZOOM = 18
const ARTERIAL_ZOOM = 17

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
      await this.withProgrammatic(() => this.moveCamera(scene, target))
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
        if (policy.controlScope) this.drawControlScope(resp, target)
        break
    }

    if (policy.downstreamTopology) this.drawDownstreamTopology(resp, target)
    if (policy.metricMarkers && target) this.drawMetricMarkers(resp, target)
    if (policy.diagnosisCompare) this.drawDiagnosisCompare(resp)
    if (policy.causeAnnotation) this.drawCauseAnnotations(resp)
    if (policy.planPreview) this.drawPlanPreview(resp, target)
  }

  /** 连贯运镜：城市→路口→车道 单调下钻(→18)；干线/控制 平滑抬升(→17)。 */
  private async moveCamera(scene: ActMapScene, target: [number, number] | null) {
    try {
      this.map.setPitch?.(scene.pitch ?? 0)
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
        // 连贯下钻到渠化详情级（≥18），只放大不回退
        const z = clampZoomUp(this.currentZoom, scene.zoom ?? CHANNELIZATION_ZOOM)
        await drillToIntersection(this.map, target, z)
        this.currentZoom = z
        break
      }
      case 'trace':
      case 'corridor': {
        if (!target) break
        // 溯源/干线：允许相对当前镜头受控降 zoom，但不低于 ARTERIAL_ZOOM
        const z = Math.max(scene.zoom ?? ARTERIAL_ZOOM, ARTERIAL_ZOOM)
        const dur = Math.abs(this.currentZoom - z) > 1 ? 1000 : 800
        await smoothPullback(this.map, target, z, dur)
        panToVisualCenter(this.map, target)
        this.currentZoom = z
        break
      }
      case 'control': {
        if (!target) break
        // 治理/控制：从干线级丝滑回到渠化详情级，便于观察控制范围叠加
        const z = clampZoomUp(this.currentZoom, scene.zoom ?? CHANNELIZATION_ZOOM)
        await drillToIntersection(this.map, target, z)
        this.currentZoom = z
        break
      }
    }
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

  /**
   * 溯源阶段：发光双层干线 + 沿线粒子 + 占比缩放节点 + 占比标签。
   * 方向由数据来源确定：entry_traces=来向(上游·琥珀)，turn_traces=去向(下游·青蓝)。
   * 仅渲染真实 path/坐标/占比（禁止前端合成，见 docs/rule.md 约束19）。
   */
  private drawTrace(resp: RunResponse | null, target: [number, number] | null) {
    this.traceLayer = new TraceLayer(this.AMap, this.map)
    if (target) this.traceLayer.revealTarget('target', target[0], target[1])

    const upstream = (resp?.phases?.diagnosis?.flow_trace?.entry_traces ?? []).map(
      (t: any): UpstreamTraceItem => ({
        upstream_inter_id: t.upstream_inter_id,
        upstream_inter_name: t.upstream_inter_name,
        upstream_lng: t.upstream_lng,
        upstream_lat: t.upstream_lat,
        dir8_code: t.dir8_code,
        path: validPath(t.path),
        dominant_movement: t.dominant_movement,
        upstream_movements: t.upstream_movements,
      }),
    )
    const scenes = resp?.phases?.diagnosis?.map_scenes ?? {}
    const sniff = (scenes as any).flow_trace_links_sniff_map as TraceSniffScene | undefined
    const legacySniff =
      sniff?.available && sniff.intersections?.length
        ? sniff
        : buildLegacySniffScene({
            target: resp?.diagnosis_ticket,
            channelizationMap: (scenes as any).channelization_map,
            upstreamTraces: resp?.phases?.diagnosis?.flow_trace?.entry_traces as any,
            downstreamTraces: (scenes as any).downstream_trace_map?.turn_traces as any,
          })
    if (legacySniff.available && legacySniff.intersections?.length) {
      this.traceLayer.renderSniffScene(legacySniff)
      return
    }

    const downstream = ((scenes as any).downstream_trace_map?.turn_traces ?? []).map(
      (t: any): DownstreamTraceItem => ({
        downstream_inter_id: t.downstream_inter_id,
        name: t.name,
        movement: t.movement,
        share_pct: t.share_pct,
        path: validPath(t.path),
        lon: t.lon,
        lat: t.lat,
        capacity: t.capacity,
      }),
    )

    this.traceLayer.renderUpstreamTraces(upstream)
    this.traceLayer.renderDownstreamTraces(downstream)
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
  }

  /** 目标路口一跳下游十字拓扑：所有真实出口 link 下游节点 + 问题转向高亮。 */
  private drawDownstreamTopology(resp: RunResponse | null, target: [number, number] | null) {
    const scenes = (resp?.phases?.diagnosis?.map_scenes ?? {}) as Record<string, any>
    const topology = buildDownstreamTopology(scenes, target)
    if (!topology.nodes.length && !topology.edges.length) return
    this.downstreamTopologyLayer = new DownstreamTopologyLayer(this.AMap, this.map)
    this.downstreamTopologyLayer.render(topology)
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
    for (const edge of (csm as any)?.coordination_paths ?? []) {
      const path = validPath(edge.path)
      if (path.length >= 2) {
        this.add(
          new this.AMap.Polyline({
            path,
            strokeColor: '#f5a623',
            strokeWeight: 4,
            strokeOpacity: 0.75,
            strokeStyle: 'dashed',
            showDir: true,
          }),
        )
      }
    }
  }

  /** act3–4：本路口 vs 主要下游双节点对比。 */
  private drawDiagnosisCompare(resp: RunResponse | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.diagnosis_compare
    if (!scene?.available) return
    for (const node of [scene.target, scene.downstream]) {
      if (!node || !hasCoord(node.lng, node.lat)) continue
      const color = node.role === 'target' ? '#ff5050' : '#38bdf8'
      const metrics = node.metrics ?? {}
      const label =
        node.role === 'target'
          ? `本路口·排队${metrics.queue_ratio ?? '—'}`
          : `下游·饱和${metrics.saturation ?? '—'}`
      this.add(this.pulseMarker([node.lng, node.lat], color, label))
    }
  }

  /** act6：主因关联空间对象 + 案例轻量标记。 */
  private drawCauseAnnotations(resp: RunResponse | null) {
    const scene = (resp?.phases?.diagnosis?.map_scenes as any)?.cause_spatial
    if (!scene?.available) return
    const reduced =
      typeof window !== 'undefined' &&
      !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    for (const ann of scene.annotations ?? []) {
      if (!hasCoord(ann.lng, ann.lat)) continue
      const color = ann.color ?? '#00e5ff'
      const label = ann.label ?? ann.case_id ?? '标注'
      this.add(this.pulseMarker([ann.lng, ann.lat], color, label))
      if (!reduced && ann.kind === 'downstream' && ann.inter_id) {
        const target = resp?.diagnosis_ticket
        if (target && hasCoord(target.lng, target.lat)) {
          this.add(
            new this.AMap.Polyline({
              path: [
                [target.lng as number, target.lat as number],
                [ann.lng, ann.lat],
              ],
              strokeColor: color,
              strokeWeight: 2,
              strokeOpacity: 0.5,
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
