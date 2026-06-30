<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CognitionPayload, IntersectionLink, MapActionEvent, MapSceneHud, MapSceneMarker, UpstreamStoryboard, UpstreamTreeNode } from '../types/map'
import { isEdgeId, visibleAtFrame } from '../utils/upstreamFrame'
import { assignLabelAnchors } from '../utils/upstreamLayout'
import {
  UPSTREAM_CHAN_FADE_MS,
  UPSTREAM_CORRIDOR_ZOOM,
  UPSTREAM_ROAD_HOLD_MS,
  upstreamFrameDuration,
} from '../utils/upstreamTiming'
import { prepareUpstreamStoryboard } from '../utils/upstreamStoryboard'
import { formatUpstreamTurnSplit } from '../utils/upstreamTurnSplit'
import { createUpstreamTraceLayer, type UpstreamTraceLayer } from '../lib/upstreamTraceLayer'
import { severityColor } from '../utils/ringSeverity'
import type { ProblemEvidence, QuantitativeConstraints } from '../types/evidence'
import type { PipelinePhase, HighlightTurn, RuntimeMetrics } from '../types/presentation'
import type { PresentationLayerGates } from '../composables/usePresentationSequence'
import ChannelizationStageOverlay from './channelization/ChannelizationStageOverlay.vue'
import { TA_THEME } from '../theme'
import {
  createDarkMap,
  flyTo,
  JINAN_CENTER,
  loadAmap,
  panToVisualCenter,
  type AMapMap,
} from '../utils/amap'
import { isEntrance, isSuppressedMapNarrativeMarker, linkStrokeColor, markerHtml, mergeSceneMarkers, normalizeDir, RUNTIME_METRIC_MAP_PHASES } from '../utils/mapMarkers'
import { buildEvidenceDirectionMarkers, buildProtectedDirectionMarkers, highlightDirsForGroup } from '../utils/evidencePresentation'
import { buildInterItemFromCognition, buildQueueDataFromEvidence } from '../utils/cognitionChannelAdapter'
import { createChannelizationController, type ChannelizationController } from '../lib/channelizationController'
import { LOD_THRESHOLDS } from '../lib/channelizationGeometry'
import { STEP_INDICES } from '../constants'

const props = defineProps<{
  mapActions: MapActionEvent[]
  highlightDirs?: string[]
  protectedDirs?: string[]
  focusedDirs?: string[]
  hudOverride?: MapSceneHud | null
  cognition?: CognitionPayload | null
  pipelinePhase?: PipelinePhase
  evidence?: ProblemEvidence | null
  highlightTurn?: HighlightTurn | null
  runtimeMetrics?: RuntimeMetrics | null
  timingRingVisible?: boolean
  corridorWaveVisible?: boolean
  showEvidenceNote?: boolean
  showGovernanceNote?: boolean
  governance?: import('../types/evidence').FlowTimingGovernance | null
  governanceSuggestion?: import('../types/presentation').GovernanceSuggestionPayload | null
  /** 新一轮分析时递增，用于重置地图浮层 */
  analysisRunKey?: number
  corridorSelectedInterId?: string | null
  /** 左侧干线列表占用时的视觉中心偏移 */
  visualPanOffsetX?: number
  presentationLayers?: PresentationLayerGates
  /** 路口信息卡激活时，抑制渠化舞台重复的顶部身份/HUD 条 */
  suppressStageHud?: boolean
  /** 后端按问题类型推导的呈现维度，门控渠化排队等图层 */
  activeDimensions?: string[]
  /** 理解过程已进入「运行数据」步骤 */
  runtimePanelRevealed?: boolean
  focusStepIndex?: number
}>()

const emit = defineEmits<{
  channelizationActive: [active: boolean]
  closeTimingRing: []
  closeCorridorWave: []
  corridorIntersectionSelect: [interId: string]
  viewChange: [view: { zoom: number; lod: 'L0' | 'L1' | 'L2' }]
  /** 上游溯源逐帧叙事，供 App 同步 TTS */
  upstreamNarration: [payload: { idx: number; text: string | null }]
}>()

/** 程序化镜头移动期间为 true，用于区分"用户手动操作"与"系统下钻" */
let programmaticMove = false
/** 用户一旦手动拖拽/缩放，后续步骤不再强制 recenter，保留其视角 */
const userInteracted = ref(false)

function lodForZoom(zoom: number): 'L0' | 'L1' | 'L2' {
  return zoom < LOD_THRESHOLDS.L1 ? 'L0' : zoom < LOD_THRESHOLDS.L2 ? 'L1' : 'L2'
}

function emitView() {
  if (!map) return
  const zoom = map.getZoom()
  const lod = lodForZoom(zoom)
  debugZoom.value = zoom
  debugLod.value = lod
  emit('viewChange', { zoom, lod })
}

/** 分析推进只前进不回退：目标 zoom 不低于当前 zoom（reset 城市视图除外） */
function clampZoomUp(target: number): number {
  if (!map) return target
  return Math.max(target, map.getZoom())
}

let programmaticDepth = 0
/** 程序化镜头操作包裹器：期间 zoomend 不计为"用户操作" */
async function withProgrammatic(fn: () => Promise<void> | void) {
  programmaticDepth++
  programmaticMove = true
  try {
    await fn()
  } finally {
    programmaticDepth--
    if (programmaticDepth === 0) programmaticMove = false
  }
}

const mapContainer = ref<HTMLElement | null>(null)
const debugZoom = ref<number | null>(null)
const debugLod = ref<'L0' | 'L1' | 'L2' | null>(null)
const ready = ref(false)
const error = ref<string | null>(null)
const cognition = ref<CognitionPayload | null>(null)
const hud = ref<MapSceneHud | null>(null)
const scenePhase = ref<string | null>(null)
const viewMode = ref<'map' | 'channelization'>('map')
const channelizationLocked = ref(false)

const effectiveCognition = computed((): CognitionPayload | null => {
  const fromProps = props.cognition
  const local = cognition.value
  if (!fromProps && !local) return null
  const base = fromProps ?? local!
  return {
    ...base,
    intersection: local?.intersection ?? fromProps?.intersection ?? base.intersection,
    arms: (local?.arms?.length ? local.arms : fromProps?.arms) ?? base.arms ?? [],
    links: (local?.links?.length ? local.links : fromProps?.links) ?? base.links,
    metrics_by_arm: local?.metrics_by_arm ?? fromProps?.metrics_by_arm ?? base.metrics_by_arm,
    metrics_by_turn: local?.metrics_by_turn ?? fromProps?.metrics_by_turn ?? base.metrics_by_turn,
    direction_groups:
      local?.direction_groups ?? fromProps?.direction_groups ?? base.direction_groups,
  }
})

const showChanFull = computed(
  () =>
    channelizationLocked.value &&
    viewMode.value === 'channelization' &&
    (effectiveCognition.value?.arms?.length ?? 0) > 0,
)

const channelHighlightDirs = computed(() =>
  props.highlightDirs?.length ? props.highlightDirs : sceneOpts.value.highlightDirs,
)

const PANEL_OFFSET_X = -120
const CORRIDOR_FOCUS_ZOOM = 16.8
const FOCUS_ZOOM = 17.8
const CITY_ZOOM = 11

let lastCorridorAction: MapActionEvent | null = null
let lastMetricSceneAction: MapActionEvent | null = null

let map: AMapMap | null = null
let AMapLib: typeof AMap | null = null
let resizeObs: ResizeObserver | null = null
let boxOverlay: InstanceType<typeof AMap.Polygon> | null = null
const linkOverlays: InstanceType<typeof AMap.Polyline>[] = []
const glowOverlays: InstanceType<typeof AMap.Polyline>[] = []
const markers: InstanceType<typeof AMap.Marker>[] = []

// —— 上游治理溯源：单链路发光干线，全自动逐路口运镜（无控制条 / 用户全程不操作） ——
let traceLayer: UpstreamTraceLayer | null = null
let upstreamStoryboard: UpstreamStoryboard | null = null
/** 递增以作废进行中的溯源动画/运镜任务 */
let upstreamEpoch = 0
const upstreamIdx = ref(0)
let upstreamTimer: ReturnType<typeof setTimeout> | null = null
let lastUpstreamCenter: [number, number] | null = null
let lastUpstreamZoom: number | null = null

const sceneOpts = ref({
  highlightDirs: [] as string[],
  protectedDirs: [] as string[],
  pulseIds: [] as string[],
  flashDirs: [] as string[],
  dimOthers: false,
})

let extraEvidenceMarkers: import('../types/map').MapSceneMarker[] = []
const chanSceneMarkers = ref<MapSceneMarker[]>([])

/* ── 主图渠化（AMap 覆盖物） ───────────────────────────────────────────────── */
let chanController: ChannelizationController | null = null
let chanMountedKey = '' // 已挂载渠化的路口标识（inter_id|arm数），变更时重建

function allowRuntimeMapMetrics(): boolean {
  const step = props.focusStepIndex ?? -1
  return Boolean(props.runtimePanelRevealed) && step >= STEP_INDICES.DATA_FETCH
}

function channelizationPhaseParams() {
  const allowRuntime = allowRuntimeMapMetrics()
  return {
    phase: props.pipelinePhase,
    cognition: effectiveCognition.value,
    evidence: props.evidence ?? null,
    runtimeMetrics: props.runtimeMetrics ?? null,
    highlightTurn: props.highlightTurn ?? null,
    highlightDirs: channelHighlightDirs.value,
    protectedDirs: props.protectedDirs ?? [],
    sceneMarkers: chanSceneMarkers.value,
    queueArms: allowRuntime
      ? buildQueueDataFromEvidence(
          effectiveCognition.value,
          props.evidence ?? null,
          props.runtimeMetrics ?? null,
        )
      : [],
    activeDimensions: props.activeDimensions,
    allowRuntimeMetrics: allowRuntime,
  }
}

function syncChannelizationPhase() {
  if (chanController?.active()) chanController.syncPhase(channelizationPhaseParams())
}

function mountChannelization() {
  if (!map || !AMapLib) return
  const cog = effectiveCognition.value
  if (!cog?.arms?.length) return
  const key = `${cog.intersection?.inter_id ?? ''}|${cog.arms.length}`
  if (!chanController) chanController = createChannelizationController(AMapLib, map)
  if (key !== chanMountedKey) {
    chanController.mount(buildInterItemFromCognition(cog))
    chanMountedKey = key
  }
  chanController.applyLOD(map.getZoom())
  syncChannelizationPhase()
}

function disposeChannelization() {
  chanController?.dispose()
  chanMountedKey = ''
}

function syncChanSceneMarkers(action?: MapActionEvent) {
  if (!channelizationLocked.value) return
  if (action) {
    if (action.phase && RUNTIME_METRIC_MAP_PHASES.has(action.phase)) {
      lastMetricSceneAction = action
    }
    if (!allowRuntimeMapMetrics()) {
      chanSceneMarkers.value = []
      syncChannelizationPhase()
      return
    }
    chanSceneMarkers.value = mergeSceneMarkers(action, cognition.value, {
      allowRuntimeMetrics: true,
    })
    syncChannelizationPhase()
  }
}

function centerMapOnIntersection(lon: number, lat: number, zoom?: number) {
  if (!map) return
  if (channelizationLocked.value) {
    // 用户已手动操作时不再强制回拉视角
    if (userInteracted.value) return
    map.setStatus({ animateEnable: false })
    if (zoom != null) map.setZoom(clampZoomUp(zoom))
    map.setCenter([lon, lat])
    return
  }
  if (zoom != null && AMapLib) {
    void flyTo(map, AMapLib, [lon, lat], zoom, 0).then(() => {
      panToVisualCenter(map!, [lon, lat], visualPanOffsetX(), 0)
    })
    return
  }
  panToVisualCenter(map, [lon, lat], visualPanOffsetX(), 0)
}

// ===== 上游治理溯源：单链路发光干线，全自动逐路口运镜 =====
function disposeUpstream() {
  upstreamEpoch += 1
  if (upstreamTimer) {
    clearTimeout(upstreamTimer)
    upstreamTimer = null
  }
  traceLayer?.dispose()
  traceLayer = null
  upstreamStoryboard = null
  upstreamIdx.value = 0
  lastUpstreamCenter = null
  lastUpstreamZoom = null
}

function findUpstreamNode(sb: UpstreamStoryboard, key: string): UpstreamTreeNode | null {
  for (const tree of sb.trees) {
    for (const node of tree.nodes) {
      if (node.id === key || node.inter_id === key) return node
    }
  }
  return null
}

function resolveEdgePath(
  sb: UpstreamStoryboard,
  edge: { from?: string | null; to?: string | null; path?: Array<[number, number]> },
): Array<[number, number]> {
  const upstream = edge.to ? findUpstreamNode(sb, edge.to) : null
  const downstream = edge.from ? findUpstreamNode(sb, edge.from) : null
  let path = (edge.path ?? []).map((p) => [p[0], p[1]] as [number, number])
  if (path.length >= 2 && upstream?.lon != null && upstream.lat != null && downstream?.lon != null && downstream.lat != null) {
    path = orientPathEndpoints(
      path,
      [upstream.lon as number, upstream.lat as number],
      [downstream.lon as number, downstream.lat as number],
    )
    return path
  }
  if (path.length >= 2) return path
  // 禁止飞线：无 geom 折线时不渲染
  return []
}

function orientPathEndpoints(
  path: Array<[number, number]>,
  start: [number, number],
  end: [number, number],
): Array<[number, number]> {
  if (path.length < 2) return path
  const dist = (a: [number, number], b: [number, number]) =>
    (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
  const forward = dist(path[0], start) + dist(path[path.length - 1], end)
  const reverse = dist(path[path.length - 1], start) + dist(path[0], end)
  const oriented = forward <= reverse ? path : [...path].reverse()
  if (dist(oriented[0], start) > dist(oriented[oriented.length - 1], start)) {
    return [...oriented].reverse()
  }
  return oriented
}

function labelsVisibleAtFrame(sb: UpstreamStoryboard, n: number, nodeId: string): boolean {
  const clamped = Math.max(0, Math.min(n, sb.frames.length - 1))
  for (let i = 0; i <= clamped; i++) {
    const f = sb.frames[i]
    if (f.show_labels === false) continue
    if (f.frame_type === 'spread' || f.frame_type === 'pullback') continue
    if (!f.reveal.includes(nodeId) || isEdgeId(nodeId)) continue
    if (!f.frame_type || f.frame_type === 'node' || f.frame_type === 'fit') return true
  }
  return false
}

/** 帧增量揭示：单链路发光干线 + 流动粒子 + 节点脉冲 + 极简标签（仅当前进口树）。 */
function renderUpstreamFrame(n: number) {
  const epoch = upstreamEpoch
  const sb = upstreamStoryboard
  if (!sb || !map || !AMapLib || !traceLayer || epoch !== upstreamEpoch) return
  const frame = sb.frames[Math.max(0, Math.min(n, sb.frames.length - 1))]
  const { overlayIds, activeTree } = visibleAtFrame(sb, n)

  // 单链路收口：非并行时只渲染当前活动进口树，避免多方向同画。
  const trees = sb.parallel ? sb.trees : sb.trees.filter((t) => t.tree_id === activeTree)

  for (const tree of trees) {
    for (const edge of tree.edges) {
      if (!overlayIds.has(edge.id) || traceLayer.hasOverlay(edge.id)) continue
      const path = resolveEdgePath(sb, edge)
      if (path.length < 2) continue
      traceLayer.revealEdge(edge.id, path, { flowPct: edge.flow_pct })
    }
  }

  const visible: Array<{ node: UpstreamTreeNode; id: string }> = []
  for (const tree of trees) {
    for (const node of tree.nodes) {
      const id = node.id ?? node.inter_id ?? ''
      if (!id || !overlayIds.has(id)) continue
      if (node.lon == null || node.lat == null) continue
      visible.push({ node, id })
    }
  }
  const anchors = assignLabelAnchors(visible.map((v) => ({ id: v.id, hop: v.node.hop })))

  for (const { node, id } of visible) {
    const isTarget = node.role === 'target'
    const isGov = node.role === 'governance' || node.decision === '治理落点'
    const role = isTarget ? 'target' : isGov ? 'governance' : 'upstream'
    traceLayer.revealNode(id, node.lon as number, node.lat as number, { role })

    // 目标（问题进口）路口只保留红色脉冲，不落指标卡，避免主路口堆叠。
    if (isTarget || !labelsVisibleAtFrame(sb, n, id)) continue

    const sat = node.saturation ?? null
    const color = isGov ? '#6dffb5' : severityColor(sat)
    const [dx, dy] = anchors[id] ?? [0, -54]
    const satTxt = typeof sat === 'number' && sat > 0.01 ? `饱和 ${sat.toFixed(2)}` : '待核查'
    const splitTxt = formatUpstreamTurnSplit(node.turn_split)
    const splitLine = splitTxt ? `<div class="us-split">${splitTxt}</div>` : ''
    const hopTxt = typeof node.hop === 'number' ? `上游${node.hop}` : '上游'
    const html =
      `<div class="us-label${isGov ? ' is-gov' : ''}">` +
      `<div class="us-hop">${hopTxt}</div>` +
      `<div class="us-name">${isGov ? '★ ' : ''}${node.name ?? id}</div>` +
      `<div class="us-metric" style="color:${color}">${satTxt}</div>` +
      `${splitLine}</div>`
    traceLayer.revealLabel(id, node.lon as number, node.lat as number, html, [dx, dy])
  }

  const narr = frame?.narration ?? null
  emit('upstreamNarration', { idx: n, text: narr })
}

function upstreamCameraSleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function cameraNearTarget(
  center: [number, number],
  zoom: number,
  centerEps = 0.0009,
  zoomEps = 0.2,
): boolean {
  if (!map) return false
  const anchor = lastUpstreamCenter
  const z = lastUpstreamZoom ?? map.getZoom()
  if (!anchor) return false
  const dist = Math.hypot(center[0] - anchor[0], center[1] - anchor[1])
  return dist < centerEps && Math.abs(zoom - z) < zoomEps
}

/** 上游溯源允许拉远 zoom（突破分析推进的 clampZoomUp 约束）。 */
async function flyToUpstreamCorridor(center: [number, number], zoom: number, duration = 1100) {
  if (!map || !AMapLib) return
  if (cameraNearTarget(center, zoom)) return
  const epoch = upstreamEpoch
  await withProgrammatic(async () => {
    if (epoch !== upstreamEpoch) return
    await flyTo(map!, AMapLib!, center, zoom, duration)
    if (epoch !== upstreamEpoch) return
    panToVisualCenter(map!, center, visualPanOffsetX(), 0)
    lastUpstreamCenter = center
    lastUpstreamZoom = zoom
  })
}

function validFrameCenter(center: [number | null, number | null] | null): [number, number] | null {
  if (!center || center[0] == null || center[1] == null) return null
  return [center[0], center[1]]
}

async function applyUpstreamFrameCamera(n: number) {
  if (!upstreamStoryboard || !map || !AMapLib || userInteracted.value) return
  const state = visibleAtFrame(upstreamStoryboard, n)
  const frame = state.frame

  if (state.fit || frame?.frame_type === 'fit') {
    const fitTargets = traceLayer?.overlays() ?? []
    if (fitTargets.length) {
      await withProgrammatic(async () => {
        map!.setFitView(fitTargets, true, [90, 120, 150, 120])
        await upstreamCameraSleep(650)
        lastUpstreamCenter = null
        lastUpstreamZoom = map!.getZoom()
      })
    }
    return
  }

  const center = validFrameCenter(state.center)
  const zoom = typeof state.zoom === 'number' ? state.zoom : null
  if (!center || zoom == null) return
  const duration = frame?.frame_type === 'spread' ? 820 : 980
  await flyToUpstreamCorridor(center, zoom, duration)
}

/** 流量溯源：从渠化视角起步，先隐渠化、清空旧高亮，再平滑过渡到溯源 zoom。 */
async function enterUpstreamFromChannelization(center: [number, number]) {
  if (!map || !AMapLib) return
  const startZoom = map.getZoom()
  lastUpstreamCenter = center
  lastUpstreamZoom = startZoom

  // 1) 淡出渠化舞台（保留当前镜头位姿）
  viewMode.value = 'map'
  await upstreamCameraSleep(UPSTREAM_CHAN_FADE_MS)

  // 2) 移除车道级渠化几何，并清空上一阶段的虚线框 / 进口道高亮 / 浮动结果卡，
  // 让单链路发光干线在干净底图上呈现（对齐参考项目「干线诊断」表达）。
  disposeChannelization()
  channelizationLocked.value = false
  chanSceneMarkers.value = []
  clearMarkers()
  clearOverlays()
  extraEvidenceMarkers = []
  scenePhase.value = 'links'
  sceneOpts.value = {
    highlightDirs: [],
    protectedDirs: [],
    pulseIds: [],
    flashDirs: [],
    dimOthers: false,
  }
  await upstreamCameraSleep(UPSTREAM_ROAD_HOLD_MS)

  // 3) 从渠化 zoom（~18.5）单次平滑过渡到溯源主视角 16.00
  const targetZoom = UPSTREAM_CORRIDOR_ZOOM
  const duration = Math.abs(startZoom - targetZoom) > 1 ? 1100 : 700
  await flyToUpstreamCorridor(center, targetZoom, duration)
}

function startUpstreamAuto() {
  if (!upstreamStoryboard?.frames.length) return
  upstreamIdx.value = 0
  void showUpstreamFrame(0)
  scheduleUpstreamTick()
}

async function showUpstreamFrame(n: number) {
  const sb = upstreamStoryboard
  const frame = sb?.frames[Math.max(0, Math.min(n, (sb?.frames.length ?? 1) - 1))]
  if (frame?.fit || frame?.frame_type === 'fit') {
    renderUpstreamFrame(n)
    await applyUpstreamFrameCamera(n)
    return
  }
  await applyUpstreamFrameCamera(n)
  renderUpstreamFrame(n)
}

function scheduleUpstreamTick() {
  if (upstreamTimer) clearTimeout(upstreamTimer)
  if (!upstreamStoryboard) return
  const epoch = upstreamEpoch
  const frame = upstreamStoryboard.frames[upstreamIdx.value]
  const delay = upstreamFrameDuration(frame)
  upstreamTimer = setTimeout(() => {
    if (epoch !== upstreamEpoch || !upstreamStoryboard) {
      upstreamTimer = null
      return
    }
    const last = upstreamStoryboard.frames.length - 1
    if (upstreamIdx.value >= last) {
      upstreamTimer = null
      return
    }
    upstreamIdx.value += 1
    void (async () => {
      await showUpstreamFrame(upstreamIdx.value)
      if (epoch === upstreamEpoch) scheduleUpstreamTick()
    })()
  }, delay)
}

async function beginUpstreamStoryboard(sb: UpstreamStoryboard, targetHint?: HighlightTurn | null) {
  disposeUpstream()
  if (map && AMapLib) traceLayer = createUpstreamTraceLayer(AMapLib, map)
  const prepared = prepareUpstreamStoryboard(sb, targetHint)
  upstreamStoryboard = prepared.storyboard
  const first = upstreamStoryboard.frames[0]
  const targetNode = upstreamStoryboard.trees[0]?.nodes.find((n) => n.role === 'target')
  const center: [number, number] | null =
    first?.center && first.center[0] != null && first.center[1] != null
      ? [first.center[0], first.center[1]]
      : targetNode?.lon != null && targetNode.lat != null
        ? [targetNode.lon, targetNode.lat]
        : null
  if (center) {
    await enterUpstreamFromChannelization(center)
  }
  startUpstreamAuto()
}

let linkFlashTimer: ReturnType<typeof setInterval> | null = null

function stopLinkFlash() {
  if (linkFlashTimer) {
    clearInterval(linkFlashTimer)
    linkFlashTimer = null
  }
}

function clearMarkers() {
  markers.forEach((m) => m.setMap(null))
  markers.length = 0
}

function clearOverlays() {
  linkOverlays.forEach((o) => o.setMap(null))
  linkOverlays.length = 0
  glowOverlays.forEach((o) => o.setMap(null))
  glowOverlays.length = 0
  boxOverlay?.setMap(null)
  boxOverlay = null
}

function boundsFromLinks(links: IntersectionLink[], center: [number, number]) {
  let minLon = center[0]
  let maxLon = center[0]
  let minLat = center[1]
  let maxLat = center[1]
  for (const link of links) {
    for (const [lon, lat] of link.path) {
      minLon = Math.min(minLon, lon)
      maxLon = Math.max(maxLon, lon)
      minLat = Math.min(minLat, lat)
      maxLat = Math.max(maxLat, lat)
    }
  }
  const pad = 0.00018
  return {
    sw: [minLon - pad, minLat - pad] as [number, number],
    ne: [maxLon + pad, maxLat + pad] as [number, number],
  }
}

function drawHighlights() {
  if (!map || !AMapLib || !cognition.value?.intersection || channelizationLocked.value) return
  // 流量溯源开始后，全程禁止诊断高亮框（红色遮罩）/进口道高亮重绘，
  // 让地图从溯源阶段起只保留单链路发光干线，直到下一轮分析重置。
  if (upstreamStoryboard) return
  clearOverlays()

  const inter = cognition.value.intersection
  const links = cognition.value.links ?? []
  const center: [number, number] = [inter.lon, inter.lat]
  const opts = sceneOpts.value

  if (links.length) {
    const { sw, ne } = boundsFromLinks(links, center)
    boxOverlay = new AMapLib.Polygon({
      path: [
        [sw[0], sw[1]],
        [ne[0], sw[1]],
        [ne[0], ne[1]],
        [sw[0], ne[1]],
      ],
      strokeColor: TA_THEME.boxStroke,
      strokeWeight: opts.pulseIds.length ? 2.5 : 2,
      strokeStyle: 'dashed',
      strokeDasharray: [8, 6],
      fillColor: opts.pulseIds.length ? 'rgba(255,80,80,0.08)' : TA_THEME.boxFill,
      fillOpacity: 0.45,
      zIndex: 50,
    })
    boxOverlay.setMap(map)
  }

  for (const link of links) {
    if (!link.path?.length) continue
    const dir = normalizeDir(link.dir4_label || '')
    const isProtected = opts.protectedDirs?.some((g) =>
      highlightDirsForGroup(g).some((d) => dir.includes(normalizeDir(d))),
    )
    const style = linkStrokeColor(link, {
      highlightDirs: opts.highlightDirs,
      protectedDirs: opts.protectedDirs,
      pulseIds: opts.pulseIds,
      flashDirs: opts.flashDirs,
      dimOthers: opts.dimOthers,
      isProtected,
    })
    const line = new AMapLib.Polyline({
      path: link.path,
      strokeColor: style.color,
      strokeWeight: style.weight,
      strokeOpacity: style.opacity,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: isEntrance(link.link_role) ? 60 : 55,
      showDir: isEntrance(link.link_role),
    })
    line.setMap(map)
    linkOverlays.push(line)

    if (style.pulse) {
      const glow = new AMapLib.Polyline({
        path: link.path,
        strokeColor: style.flash ? '#ffe566' : '#ff8a8a',
        strokeWeight: style.weight + 8,
        strokeOpacity: style.flash ? 0.38 : 0.22,
        lineJoin: 'round',
        lineCap: 'round',
        zIndex: 54,
      })
      glow.setMap(map)
      glowOverlays.push(glow)
    }
  }
}

function markerAnchor(dir?: string): string {
  const d = dir || ''
  if (d.includes('东')) return 'bottom-left'
  if (d.includes('西')) return 'bottom-right'
  if (d.includes('南')) return 'top-center'
  if (d.includes('北')) return 'bottom-center'
  return 'bottom-center'
}

function renderMarkers(action: MapActionEvent) {
  if (!map || !AMapLib || channelizationLocked.value) return
  clearMarkers()
  const isCorridor = scenePhase.value === 'corridor_scan'
  const selectedId = props.corridorSelectedInterId
  const merged = [
    ...mergeSceneMarkers(action, cognition.value, {
      allowRuntimeMetrics: allowRuntimeMapMetrics(),
    }),
    ...extraEvidenceMarkers,
  ].filter((m) => !isSuppressedMapNarrativeMarker(m)).map((m) => {
    if (!isCorridor || !m.inter_id) return m
    return { ...m, selected: m.inter_id === selectedId }
  })
  merged.forEach((m) => {
    const marker = new AMapLib.Marker({
      position: [m.lon, m.lat],
      anchor: isCorridor ? 'center' : markerAnchor(m.dir),
      content: markerHtml(m),
      zIndex:
        m.selected && isCorridor
          ? 230
          : m.kind === 'suggestion'
            ? 220
            : m.kind === 'evidence'
              ? 210
              : m.kind === 'link-info'
                ? 195
                : isCorridor
                  ? 205
                  : 200,
      offset: new AMapLib.Pixel(0, isCorridor ? 0 : -6),
    })
    if (isCorridor && m.inter_id) {
      marker.on('click', () => {
        emit('corridorIntersectionSelect', m.inter_id!)
      })
    }
    marker.setMap(map)
    markers.push(marker)
  })
}

function drawCorridorPaths(action: MapActionEvent) {
  if (!map || !AMapLib) return
  const polyline = action.corridor?.polyline ?? []
  if (polyline.length < 2) return

  const glow = new AMapLib.Polyline({
    path: polyline,
    strokeColor: '#00e5ff',
    strokeWeight: 14,
    strokeOpacity: 0.18,
    lineJoin: 'round',
    lineCap: 'round',
    zIndex: 48,
  })
  glow.setMap(map)
  glowOverlays.push(glow)

  const line = new AMapLib.Polyline({
    path: polyline,
    strokeColor: '#00e5ff',
    strokeWeight: 5,
    strokeOpacity: 0.92,
    lineJoin: 'round',
    lineCap: 'round',
    zIndex: 55,
  })
  line.setMap(map)
  linkOverlays.push(line)
}

function corridorPanOffsetX(): number {
  if (channelizationLocked.value) return 0
  return props.visualPanOffsetX ?? PANEL_OFFSET_X
}

function visualPanOffsetX(): number {
  return corridorPanOffsetX()
}

async function focusCorridorIntersection(lon: number, lat: number, zoom = CORRIDOR_FOCUS_ZOOM) {
  if (!map || !AMapLib || channelizationLocked.value) return
  await withProgrammatic(async () => {
    await flyTo(map!, AMapLib!, [lon, lat], zoom, 750)
    panToVisualCenter(map!, [lon, lat], corridorPanOffsetX(), 0)
  })
}

async function resetMapVisualState(options?: { clearCognition?: boolean }) {
  stopLinkFlash()
  disposeUpstream()
  disposeChannelization()
  userInteracted.value = false
  channelizationLocked.value = false
  viewMode.value = 'map'
  hud.value = null
  scenePhase.value = null
  lastCorridorAction = null
  lastMetricSceneAction = null
  extraEvidenceMarkers = []
  chanSceneMarkers.value = []
  sceneOpts.value = {
    highlightDirs: [],
    protectedDirs: [],
    pulseIds: [],
    flashDirs: [],
    dimOthers: false,
  }
  clearMarkers()
  clearOverlays()
  if (map) {
    map.clearMap()
  }
  if (options?.clearCognition !== false) {
    cognition.value = null
  }
}

async function prepareNewAnalysisRun() {
  await resetMapVisualState({ clearCognition: false })
}

async function resetToCityDefault() {
  if (!map || !AMapLib) return
  await resetMapVisualState()
  await flyTo(map, AMapLib, JINAN_CENTER, CITY_ZOOM, 900)
}

async function drillToIntersection(lon: number, lat: number) {
  if (!map || !AMapLib) return
  if (userInteracted.value) {
    // 用户已自行设定视角：只平移到路口，不强制重新下钻
    panToVisualCenter(map, [lon, lat], visualPanOffsetX(), 0)
    return
  }
  // 单调递增、连续下钻：从当前 zoom 起只放大不回退
  const steps = [14, 16.2, 17.5].map((z) => clampZoomUp(z))
  for (const z of steps) {
    await flyTo(map, AMapLib, [lon, lat], z, 700)
  }
  panToVisualCenter(map, [lon, lat], visualPanOffsetX(), 0)
}

async function enterChannelizationView(lon: number, lat: number) {
  if (!map || !AMapLib) return
  // 续接当前镜头，平滑放大到车道级；不打断、不回跳
  if (!userInteracted.value) {
    await flyTo(map, AMapLib, [lon, lat], clampZoomUp(18.5), 800)
  }
  stopLinkFlash()
  clearMarkers()
  clearOverlays()
  channelizationLocked.value = true
  viewMode.value = 'channelization'
  // 已在目标位姿，无需再 setZoom 造成跳变；仅在用户未介入时对齐中心
  if (!userInteracted.value) panToVisualCenter(map, [lon, lat], visualPanOffsetX(), 0)
  mountChannelization()
}

async function focusPoint(lon: number, lat: number, zoom: number) {
  if (!map || !AMapLib || channelizationLocked.value) return
  if (userInteracted.value) return
  await flyTo(map, AMapLib, [lon, lat], clampZoomUp(zoom), 900)
  panToVisualCenter(map, [lon, lat], visualPanOffsetX(), 0)
}

async function focusIntersection(lon: number, lat: number, zoom = FOCUS_ZOOM) {
  await focusPoint(lon, lat, zoom)
}

async function applyCorridorScanScene(action: MapActionEvent) {
  scenePhase.value = action.phase ?? 'corridor_scan'
  hud.value = props.hudOverride ?? action.hud ?? null
  channelizationLocked.value = false
  viewMode.value = 'map'
  cognition.value = null
  stopLinkFlash()
  clearMarkers()
  clearOverlays()
  lastCorridorAction = action

  drawCorridorPaths(action)
  renderMarkers(action)

  const center = action.center ?? action.camera?.center
  const zoom = action.zoom ?? action.camera?.zoom ?? CORRIDOR_FOCUS_ZOOM
  if (map && AMapLib && center) {
    await flyTo(map, AMapLib, center, zoom, 900)
    panToVisualCenter(map, center, corridorPanOffsetX(), 0)
  }
}

async function applyMapScene(action: MapActionEvent) {
  scenePhase.value = action.phase ?? null
  hud.value = props.hudOverride ?? action.hud ?? null

  sceneOpts.value = {
    highlightDirs: action.highlight_dirs ?? [],
    protectedDirs: action.protected_groups ?? props.protectedDirs ?? [],
    pulseIds: action.pulse_link_ids ?? [],
    flashDirs: [],
    dimOthers: action.dim_other_links ?? false,
  }

  if (channelizationLocked.value) {
    clearMarkers()
    clearOverlays()
    syncChanSceneMarkers(action)
    const inter = cognition.value?.intersection
    if (inter) {
      centerMapOnIntersection(inter.lon, inter.lat, action.zoom ?? FOCUS_ZOOM)
    }
    return
  }

  drawHighlights()
  renderMarkers(action)

  const inter = cognition.value?.intersection
  const zoom = action.zoom ?? FOCUS_ZOOM

  if (action.focus?.lon != null && action.focus?.lat != null) {
    await focusPoint(action.focus.lon, action.focus.lat, zoom)
    return
  }
  if (inter) {
    await focusIntersection(inter.lon, inter.lat, zoom)
  }
}

async function handleAction(action: MapActionEvent) {
  if (!map || !AMapLib) return

  switch (action.action) {
    case 'fly_to_intersection': {
      const inter = action.intersection
      if (!inter) return
      viewMode.value = 'map'
      disposeChannelization()
      channelizationLocked.value = false
      stopLinkFlash()
      hud.value = null
      scenePhase.value = null
      clearMarkers()
      clearOverlays()
      sceneOpts.value = { highlightDirs: [], protectedDirs: [], pulseIds: [], flashDirs: [], dimOthers: false }
      cognition.value = {
        intersection: inter,
        arms: action.arms ?? cognition.value?.arms ?? [],
        links: action.links ?? cognition.value?.links ?? [],
        metrics_by_arm: action.metrics_by_arm ?? cognition.value?.metrics_by_arm,
        metrics_by_turn: action.metrics_by_turn ?? cognition.value?.metrics_by_turn,
      }
      await drillToIntersection(inter.lon, inter.lat)
      break
    }
    case 'highlight_links': {
      cognition.value = {
        intersection: action.intersection!,
        arms: action.arms ?? [],
        links: action.links ?? [],
        metrics_by_arm: action.metrics_by_arm ?? cognition.value?.metrics_by_arm,
        metrics_by_turn: action.metrics_by_turn ?? cognition.value?.metrics_by_turn,
        direction_groups: action.direction_groups ?? cognition.value?.direction_groups,
      }
      const inter = action.intersection!
      sceneOpts.value = {
        highlightDirs: [],
        protectedDirs: [],
        pulseIds: [],
        flashDirs: [],
        dimOthers: false,
      }
      await nextTick()
      await enterChannelizationView(inter.lon, inter.lat)
      syncChanSceneMarkers()
      break
    }
    case 'update_metrics': {
      if (!cognition.value) return
      cognition.value = {
        ...cognition.value,
        metrics_by_arm: action.metrics_by_arm ?? cognition.value.metrics_by_arm,
        metrics_by_turn: action.metrics_by_turn ?? cognition.value.metrics_by_turn,
        direction_groups: action.direction_groups ?? cognition.value.direction_groups,
        arms: action.arms?.length ? action.arms : cognition.value.arms,
      }
      if (!channelizationLocked.value) drawHighlights()
      break
    }
    case 'reset_city_view': {
      await resetToCityDefault()
      break
    }
    case 'map_scene': {
      await applyMapScene(action)
      break
    }
    case 'corridor_scan_scene': {
      await applyCorridorScanScene(action)
      break
    }
    case 'upstream_tree': {
      const sb = action.storyboard
      if (!sb || !sb.frames?.length) break
      await beginUpstreamStoryboard(sb, action.highlight_turn ?? props.highlightTurn ?? null)
      break
    }
    default:
      break
  }
}

watch(
  () => props.analysisRunKey,
  () => {
    void prepareNewAnalysisRun()
  },
)

watch(
  () => props.mapActions.length,
  async (len, prev) => {
    if (len <= (prev ?? 0)) return
    await withProgrammatic(() => handleAction(props.mapActions[len - 1]))
  },
)

watch(
  showChanFull,
  (active) => {
    emit('channelizationActive', active)
  },
  { immediate: true },
)

// 渠化态：阶段/证据/高亮变化时，重建（若换路口）并同步标注
watch(
  () => [
    props.pipelinePhase,
    props.evidence,
    props.highlightTurn,
    props.runtimeMetrics,
    props.highlightDirs,
    props.protectedDirs,
    props.runtimePanelRevealed,
    props.focusStepIndex,
    chanSceneMarkers.value,
    effectiveCognition.value,
  ],
  () => {
    if (!channelizationLocked.value) return
    mountChannelization()
  },
  { deep: true },
)

watch(
  () => props.runtimePanelRevealed,
  (revealed) => {
    if (!channelizationLocked.value) return
    if (!revealed) {
      chanSceneMarkers.value = []
      syncChannelizationPhase()
      return
    }
    if (lastMetricSceneAction) {
      syncChanSceneMarkers(lastMetricSceneAction)
    } else {
      syncChannelizationPhase()
    }
    if (cognition.value && scenePhase.value && !channelizationLocked.value) {
      renderMarkers({ action: 'map_scene', phase: scenePhase.value ?? 'evidence' })
    }
  },
)

watch(
  () => [props.highlightDirs, props.protectedDirs, props.focusedDirs, props.hudOverride],
  () => {
    if (channelizationLocked.value) return
    if (props.highlightDirs?.length) {
      sceneOpts.value = {
        ...sceneOpts.value,
        highlightDirs: [...props.highlightDirs],
      }
    }
    if (props.protectedDirs?.length) {
      sceneOpts.value = {
        ...sceneOpts.value,
        protectedDirs: [...props.protectedDirs],
      }
    }
    drawHighlights()
    if (cognition.value) {
      renderMarkers({ action: 'map_scene', phase: scenePhase.value ?? 'evidence' })
    }
  },
  { deep: true },
)

/** 由父组件注入证据/约束 marker */
function setEvidenceOverlay(
  evidence: ProblemEvidence | null,
  constraints: QuantitativeConstraints | null,
) {
  if (!cognition.value) {
    extraEvidenceMarkers = []
    return
  }
  const markers = evidence ? buildEvidenceDirectionMarkers(evidence, cognition.value) : []
  const protectedMarkers = constraints?.constraints
    ? buildProtectedDirectionMarkers(
        constraints.protected_directions ?? [],
        cognition.value,
        constraints.constraints,
      )
    : []
  extraEvidenceMarkers = [...markers, ...protectedMarkers]
  if (channelizationLocked.value) {
    return
  }
  drawHighlights()
  renderMarkers({ action: 'map_scene', phase: 'evidence' })
}

onMounted(async () => {
  try {
    AMapLib = await loadAmap()
    if (!mapContainer.value) return
    map = createDarkMap(mapContainer.value, AMapLib)
    ready.value = true

    map.on('zoomchange', () => {
      if (!map) return
      debugZoom.value = map.getZoom()
      debugLod.value = lodForZoom(map.getZoom())
    })
    // 渠化态随地图缩放下钻（L0 路网 / L1 轮廓 / L2 车道渠化）
    map.on('zoomend', () => {
      if (channelizationLocked.value) chanController?.applyLOD(map!.getZoom())
      if (!programmaticMove) userInteracted.value = true
      emitView()
    })
    // 用户手动拖拽后，后续步骤不再强制回拉视角
    map.on('dragend', () => {
      userInteracted.value = true
    })
    emitView()

    resizeObs = new ResizeObserver(() => {
      const inter = cognition.value?.intersection
      if (!inter || !map) return
      centerMapOnIntersection(inter.lon, inter.lat)
    })
    resizeObs.observe(mapContainer.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
})

onUnmounted(() => {
  stopLinkFlash()
  disposeChannelization()
  disposeUpstream()
  clearMarkers()
  clearOverlays()
  resizeObs?.disconnect()
  map?.destroy()
})

defineExpose({
  resetToCityDefault,
  setEvidenceOverlay,
  prepareNewAnalysisRun,
  focusCorridorIntersection,
})

watch(
  () => props.corridorSelectedInterId,
  (interId, prev) => {
    if (!interId || interId === prev || scenePhase.value !== 'corridor_scan') return
    if (lastCorridorAction) {
      renderMarkers(lastCorridorAction)
    }
    const marker = lastCorridorAction?.markers?.find((m) => m.inter_id === interId)
    if (marker?.lon != null && marker?.lat != null) {
      void focusCorridorIntersection(marker.lon, marker.lat)
    }
  },
)
</script>

<template>
  <div class="map-stage" :class="{ 'chan-mode': showChanFull }">
    <div v-if="error" class="map-error">{{ error }}</div>
    <div
      ref="mapContainer"
      class="map-canvas"
      :class="{ 'map-blended': showChanFull }"
    />

    <Transition name="hud-fade">
      <div
        v-if="(hudOverride ?? hud) && !showChanFull"
        class="map-hud"
        :class="`phase-${scenePhase}`"
      >
        <div class="hud-head">
          <span v-if="(hudOverride ?? hud)?.icon" class="hud-icon">{{ (hudOverride ?? hud)?.icon }}</span>
          <span class="hud-title">{{ (hudOverride ?? hud)?.title }}</span>
        </div>
        <div class="hud-metrics">
          <div
            v-for="(m, i) in (hudOverride ?? hud)?.metrics ?? []"
            :key="i"
            class="hud-metric"
            :class="`sev-${m.severity || 'unknown'}`"
          >
            <span class="hud-label">{{ m.label }}</span>
            <span class="hud-value">{{ m.value }}</span>
          </div>
        </div>
      </div>
    </Transition>

    <ChannelizationStageOverlay
      :visible="showChanFull"
      :fullscreen="true"
      :cognition="effectiveCognition"
      :highlight-dirs="channelHighlightDirs"
      :protected-dirs="props.protectedDirs"
      :evidence="evidence"
      :phase="pipelinePhase"
      :highlight-turn="highlightTurn"
      :runtime-metrics="runtimeMetrics"
      :timing-ring-visible="timingRingVisible"
      :corridor-wave-visible="corridorWaveVisible"
      :show-evidence-note="showEvidenceNote"
      :show-governance-note="showGovernanceNote"
      :governance="governance"
      :governance-suggestion="governanceSuggestion"
      :scene-markers="chanSceneMarkers"
      :hud="(hudOverride ?? hud) as MapSceneHud | null"
      :run-key="props.analysisRunKey ?? 0"
      :presentation-layers="presentationLayers"
      :suppress-hud="suppressStageHud"
      @close-timing-ring="emit('closeTimingRing')"
      @close-corridor-wave="emit('closeCorridorWave')"
    />

    <div v-if="!ready && !error && viewMode === 'map'" class="map-loading">地图加载中…</div>

    <div v-if="ready && debugZoom != null" class="map-zoom-debug" aria-hidden="true">
      zoom {{ debugZoom.toFixed(2) }}<span v-if="debugLod"> · {{ debugLod }}</span>
    </div>
  </div>
</template>

<style scoped>
.map-stage {
  position: relative;
  width: 100%;
  height: 100%;
  background: #020810;
  overflow: hidden;
}

.map-zoom-debug {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 40;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(0, 10, 20, 0.82);
  border: 1px solid rgba(0, 212, 240, 0.35);
  color: #9ee8ff;
  font-family: 'Courier New', Courier, monospace;
  font-size: 11px;
  line-height: 1.2;
  pointer-events: none;
  user-select: none;
}

.upstream-narration {
  position: absolute;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  z-index: 32;
  margin: 0;
  max-width: min(72%, 560px);
  padding: 9px 16px;
  border-radius: 8px;
  background: rgba(8, 12, 20, 0.9);
  border-left: 3px solid #7ec8ff;
  color: #d6ecff;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
}
.us-fade-enter-active,
.us-fade-leave-active {
  transition: opacity 0.35s ease;
}
.us-fade-enter-from,
.us-fade-leave-to {
  opacity: 0;
}

.map-stage.chan-mode {
  background: transparent;
}

.map-canvas {
  width: 100%;
  height: 100%;
  transition: opacity 0.5s ease;
}

.map-canvas.map-blended {
  opacity: 1;
  visibility: visible;
}

.map-canvas.map-fade-out {
  opacity: 0;
  pointer-events: none;
}

.chan-hud {
  top: auto;
  bottom: 16px;
  left: 16px;
  z-index: 20;
}

.map-hud {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 12;
  min-width: 160px;
  max-width: 220px;
  padding: 6px 10px;
  background: rgba(0, 10, 20, 0.88);
  border: 1px solid rgba(0, 212, 240, 0.28);
  border-left: 2px solid #00d4f0;
  backdrop-filter: blur(8px);
  pointer-events: none;
  font-family: 'Courier New', Courier, monospace;
}

.hud-head {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.hud-icon {
  font-size: 12px;
}

.hud-title {
  font-size: 10px;
  letter-spacing: 0.6px;
  color: rgba(0, 229, 255, 0.9);
  text-transform: uppercase;
}

.hud-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
}

.hud-metric {
  display: flex;
  flex-direction: column;
  gap: 1px;
  font-size: 9px;
}

.hud-label {
  color: rgba(220, 240, 255, 0.45);
  line-height: 1.2;
}

.hud-value {
  color: rgba(220, 240, 255, 0.9);
  font-weight: 700;
  font-size: 11px;
  line-height: 1.2;
}

.hud-metric.sev-high .hud-value {
  color: #ff7b7b;
}

.hud-metric.sev-medium .hud-value {
  color: #ffc266;
}

.hud-metric.sev-low .hud-value {
  color: #6dffb5;
}

.hud-fade-enter-active,
.hud-fade-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.hud-fade-enter-from,
.hud-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.map-loading,
.map-error {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  z-index: 10;
  color: rgba(220, 240, 255, 0.55);
  background: rgba(2, 8, 16, 0.85);
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
}

.map-error {
  color: #ff8a8a;
}
</style>

<style>
/* 上游溯源（单链路发光干线）：节点脉冲 + 流动粒子 + 极简标签（全局，注入 HTML） */
.us-node {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f5a623;
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 14px rgba(245, 166, 35, 0.78), 0 0 34px rgba(245, 166, 35, 0.26);
  transition: opacity 0.45s ease;
}
.us-node::after {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid currentColor;
  color: rgba(245, 166, 35, 0.72);
  animation: us-node-ripple 2.2s ease-out infinite;
}
.us-node.is-gov {
  background: #2ed573;
  box-shadow: 0 0 16px rgba(46, 213, 115, 0.78), 0 0 36px rgba(46, 213, 115, 0.22);
}
.us-node.is-gov::after {
  color: rgba(46, 213, 115, 0.68);
}
.us-node.is-target {
  width: 18px;
  height: 18px;
  background: #ff4757;
  box-shadow: 0 0 18px rgba(255, 71, 87, 0.9), 0 0 44px rgba(255, 71, 87, 0.32);
}
.us-node.is-target::after {
  inset: -11px;
  color: rgba(255, 71, 87, 0.82);
}
.us-node.is-dim {
  opacity: 0.35;
}
.us-node.is-dim::after {
  animation: none;
}
@keyframes us-node-ripple {
  0% {
    opacity: 0.88;
    transform: scale(0.45);
  }
  75%,
  100% {
    opacity: 0;
    transform: scale(2.15);
  }
}
.us-particle {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff4d6;
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 0 12px rgba(255, 207, 122, 0.95), 0 0 24px rgba(245, 166, 35, 0.5);
}
.us-label {
  min-width: 78px;
  max-width: 150px;
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(245, 166, 35, 0.42);
  background: rgba(6, 12, 24, 0.94);
  white-space: nowrap;
  font-family: 'Inter', system-ui, sans-serif;
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.42);
}
.us-label.is-gov {
  border-color: rgba(46, 213, 115, 0.5);
}
.us-label .us-hop {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: #ffcf7a;
}
.us-label.is-gov .us-hop {
  color: #6dffb5;
}
.us-label .us-name {
  font-size: 12px;
  font-weight: 700;
  color: #eaf4ff;
  line-height: 1.3;
}
.us-label .us-metric {
  font-size: 10px;
  font-weight: 700;
  margin-top: 1px;
  line-height: 1.35;
}
.us-label .us-split {
  font-size: 9px;
  font-weight: 600;
  margin-top: 2px;
  color: #c8d8ee;
  line-height: 1.35;
  white-space: normal;
}

/* 高德 Marker 气泡（全局，注入 HTML） */
.map-marker {
  position: relative;
  padding: 6px 10px 8px;
  border-radius: 2px;
  background: rgba(0, 10, 20, 0.92);
  border: 1px solid rgba(0, 212, 240, 0.45);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
  text-align: center;
  font-family: 'Courier New', Courier, monospace;
  white-space: nowrap;
  animation: marker-pop 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}

.map-marker::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -6px;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: rgba(0, 212, 240, 0.45);
}

.map-marker.sev-high {
  border-color: rgba(255, 100, 100, 0.7);
  box-shadow: 0 0 16px rgba(255, 80, 80, 0.35);
}

.map-marker.sev-high::after {
  border-top-color: rgba(255, 100, 100, 0.7);
}

.map-marker.link-info {
  border-style: dashed;
  border-color: rgba(0, 229, 255, 0.55);
  background: rgba(0, 16, 28, 0.94);
  min-width: 72px;
}

.map-marker.link-info .marker-badge {
  color: #00e5ff;
  border-color: rgba(0, 229, 255, 0.35);
}

.map-marker.metric.saturation {
  border-left: 3px solid #ff7b7b;
  background: rgba(28, 8, 8, 0.92);
}

.map-marker.metric.saturation .marker-badge {
  color: #ff9b9b;
  border-color: rgba(255, 120, 120, 0.35);
}

.map-marker.imbalance {
  border-left: 3px solid #ffc266;
  background: rgba(24, 18, 0, 0.92);
}

.map-marker.imbalance .marker-badge {
  color: #ffc266;
}

.map-marker.delay {
  border-left: 3px solid #b39dff;
  background: rgba(16, 8, 28, 0.92);
}

.map-marker.delay .marker-icon {
  color: #c9b3ff;
  font-size: 12px;
}

.map-marker.direction {
  border-color: rgba(109, 255, 181, 0.55);
  background: rgba(0, 20, 14, 0.92);
}

.map-marker.direction .marker-compass {
  font-size: 12px;
  line-height: 1;
  margin-bottom: 2px;
}

.map-marker .marker-badge {
  display: inline-block;
  margin-bottom: 4px;
  padding: 1px 5px;
  font-size: 8px;
  letter-spacing: 0.8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  color: rgba(220, 240, 255, 0.55);
}

.map-marker.dir-东::after {
  left: 12px;
}

.map-marker.dir-西::after {
  left: auto;
  right: 12px;
  transform: none;
}

.map-marker.evidence {
  border-color: rgba(255, 194, 102, 0.65);
  background: rgba(24, 18, 0, 0.92);
}

.map-marker.protected {
  border-color: rgba(109, 255, 181, 0.55);
  border-style: dashed;
  background: rgba(0, 20, 14, 0.92);
}

.map-marker.protected .marker-badge {
  color: #6dffb5;
}

.map-marker.evidence .marker-arrow {
  color: #ffc266;
  font-size: 14px;
  line-height: 1;
}

.map-marker.suggestion {
  border-color: rgba(109, 255, 181, 0.65);
  background: rgba(0, 24, 16, 0.94);
}

.map-marker.suggestion .marker-arrow {
  color: #6dffb5;
  font-size: 16px;
  line-height: 1;
  animation: arrow-bounce 1.2s ease-in-out infinite;
}

.map-marker.alert .marker-pulse {
  position: absolute;
  inset: -4px;
  border: 1px solid rgba(255, 100, 100, 0.5);
  border-radius: 2px;
  animation: pulse-ring 1.4s ease-out infinite;
}

.map-marker .marker-value {
  font-size: 16px;
  font-weight: 800;
  color: #00e5ff;
  line-height: 1.2;
}

.map-marker.sev-high .marker-value {
  color: #ff7b7b;
}

.map-marker .marker-title {
  font-size: 10px;
  color: rgba(220, 240, 255, 0.75);
  margin-top: 2px;
  letter-spacing: 0.5px;
}

.map-marker .marker-sub {
  font-size: 9px;
  color: rgba(220, 240, 255, 0.45);
  margin-top: 2px;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.map-marker.rule .marker-icon {
  color: #ffc266;
  font-size: 14px;
}

.map-marker.timing {
  border-color: rgba(255, 138, 128, 0.55);
  background: rgba(40, 8, 8, 0.88);
}

.map-marker.timing .marker-badge {
  color: #ff8a80;
}

.map-marker.corridor {
  border-color: rgba(0, 230, 118, 0.45);
  background: rgba(0, 24, 16, 0.9);
}

.map-marker.corridor.corridor-current {
  border-color: #00e5ff;
  box-shadow: 0 0 12px rgba(0, 229, 255, 0.35);
}

.map-marker.corridor .marker-badge {
  color: #69f0ae;
}

.map-marker.corridor-pin {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid rgba(0, 229, 255, 0.55);
  background: rgba(8, 20, 32, 0.92);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.map-marker.corridor-pin:hover {
  transform: scale(1.08);
}

.map-marker.corridor-pin.selected {
  border-color: #00e5ff;
  box-shadow: 0 0 14px rgba(0, 229, 255, 0.45);
  transform: scale(1.12);
}

.map-marker.corridor-pin.sev-high {
  border-color: rgba(255, 100, 100, 0.85);
  background: rgba(40, 10, 10, 0.94);
}

.map-marker.corridor-pin.sev-medium {
  border-color: rgba(255, 180, 80, 0.75);
}

.map-marker.corridor-pin.no-data {
  opacity: 0.55;
  border-style: dashed;
}

.map-marker.corridor-pin .pin-rank {
  font-size: 9px;
  line-height: 1;
  color: rgba(0, 229, 255, 0.75);
}

.map-marker.corridor-pin .pin-value {
  font-size: 11px;
  font-weight: 700;
  line-height: 1.1;
  color: #f0f8ff;
}

.map-marker.corridor-scan {
  border-color: rgba(255, 138, 100, 0.55);
  background: rgba(28, 12, 8, 0.92);
  min-width: 108px;
}

.map-marker.corridor-scan.sev-high {
  border-color: rgba(255, 100, 100, 0.75);
}

.map-marker.corridor-scan.no-data {
  opacity: 0.75;
}

.map-marker.corridor-scan .marker-badge {
  color: #ffb74d;
}

@keyframes marker-pop {
  from {
    opacity: 0;
    transform: scale(0.85) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

@keyframes pulse-ring {
  0% {
    opacity: 0.8;
    transform: scale(1);
  }
  100% {
    opacity: 0;
    transform: scale(1.25);
  }
}

@keyframes arrow-bounce {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}
</style>
