<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CognitionPayload, IntersectionLink, MapActionEvent, MapSceneHud, MapSceneMarker } from '../types/map'
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
import { isEntrance, linkStrokeColor, markerHtml, mergeSceneMarkers, normalizeDir, RUNTIME_METRIC_MAP_PHASES } from '../utils/mapMarkers'
import { buildEvidenceDirectionMarkers, buildProtectedDirectionMarkers, highlightDirsForGroup } from '../utils/evidencePresentation'
import { buildInterItemFromCognition } from '../utils/cognitionChannelAdapter'
import { createChannelizationController, type ChannelizationController } from '../lib/channelizationController'
import { LOD_THRESHOLDS } from '../lib/channelizationGeometry'

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
  /** 理解过程进入「运行数据」步骤后为 true；此前不展示地图饱和度卡 */
  runtimePanelRevealed?: boolean
}>()

const emit = defineEmits<{
  channelizationActive: [active: boolean]
  closeTimingRing: []
  closeCorridorWave: []
  corridorIntersectionSelect: [interId: string]
  viewChange: [view: { zoom: number; lod: 'L0' | 'L1' | 'L2' }]
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
  emit('viewChange', { zoom, lod: lodForZoom(zoom) })
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
const flowSourceMarkers: InstanceType<typeof AMap.Marker>[] = []
const flowSourceLines: InstanceType<typeof AMap.Polyline>[] = []

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

function channelizationPhaseParams() {
  return {
    phase: props.pipelinePhase,
    cognition: effectiveCognition.value,
    evidence: props.evidence ?? null,
    runtimeMetrics: props.runtimeMetrics ?? null,
    highlightTurn: props.highlightTurn ?? null,
    highlightDirs: channelHighlightDirs.value,
    protectedDirs: props.protectedDirs ?? [],
    sceneMarkers: chanSceneMarkers.value,
    allowRuntimeMetrics: Boolean(props.runtimePanelRevealed),
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
    if (!props.runtimePanelRevealed) {
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

function clearFlowSources() {
  flowSourceMarkers.forEach((m) => m.setMap(null))
  flowSourceMarkers.length = 0
  flowSourceLines.forEach((l) => l.setMap(null))
  flowSourceLines.length = 0
}

/** 流量溯源：沿进口道折线展示上一跳来车方向（禁止中心飞线） */
function renderFlowSources(action: MapActionEvent) {
  if (!map || !AMapLib) return
  clearFlowSources()
  const traces = action.entry_traces ?? []
  const center = action.source_center
  const palette = ['#ff8a4c', '#ffc266', '#ff6b9d', '#7ec8ff']
  traces.forEach((trace, idx) => {
    const color = palette[idx % palette.length]
    let path: Array<[number, number]> = []
    if (trace.path && trace.path.length >= 2) {
      path = trace.path.map((p) => [p[0], p[1]] as [number, number])
    } else if (
      trace.lon != null &&
      trace.lat != null &&
      center?.lon != null &&
      center?.lat != null
    ) {
      path = [
        [trace.lon, trace.lat],
        [center.lon, center.lat],
      ]
    }
    if (path.length < 2) return
    const weight = 2.5 + Math.min(4, (trace.vehicles_of_100 ?? 50) / 25)
    const line = new AMapLib.Polyline({
      path,
      strokeColor: color,
      strokeWeight: weight,
      strokeOpacity: 0.82,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: true,
      zIndex: 68 + idx,
    })
    line.setMap(map)
    flowSourceLines.push(line)
    const tip = path[0]
    const label =
      `${trace.entry ?? ''} ← ${trace.name ?? '上一路口'} ` +
      `${trace.dominant_turn ?? ''} ${trace.vehicles_of_100 ?? ''}辆/100`
    const marker = new AMapLib.Marker({
      position: tip,
      anchor: 'bottom-center',
      zIndex: 78 + idx,
      content:
        `<div class="flow-road-label" style="border-color:${color}">` +
        `<span>${label.trim()}</span></div>`,
    })
    marker.setMap(map)
    flowSourceMarkers.push(marker)
  })
  if (flowSourceLines.length) {
    try {
      map.setFitView([...flowSourceLines], true, [100, 100, 160, 100])
    } catch {
      /* best-effort */
    }
  }
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
      allowRuntimeMetrics: Boolean(props.runtimePanelRevealed),
    }),
    ...extraEvidenceMarkers,
  ].map((m) => {
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

async function prepareNewAnalysisRun() {
  stopLinkFlash()
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
  clearFlowSources()
}

async function resetToCityDefault() {
  if (!map || !AMapLib) return
  stopLinkFlash()
  disposeChannelization()
  userInteracted.value = false
  channelizationLocked.value = false
  viewMode.value = 'map'
  cognition.value = null
  hud.value = null
  scenePhase.value = null
  clearMarkers()
  clearOverlays()
  sceneOpts.value = { highlightDirs: [], protectedDirs: [], pulseIds: [], flashDirs: [], dimOthers: false }
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
    case 'highlight_flow_sources':
      break
    case 'map_scene': {
      await applyMapScene(action)
      break
    }
    case 'corridor_scan_scene': {
      await applyCorridorScanScene(action)
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
  clearMarkers()
  clearOverlays()
  resizeObs?.disconnect()
  map?.destroy()
})

defineExpose({ resetToCityDefault, setEvidenceOverlay, prepareNewAnalysisRun, focusCorridorIntersection })

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
.flow-road-label {
  padding: 3px 7px;
  border-radius: 3px;
  border: 1px solid rgba(255, 138, 76, 0.7);
  background: rgba(10, 14, 22, 0.9);
  font-size: 10px;
  font-weight: 600;
  color: #ffe8cc;
  white-space: nowrap;
  font-family: 'Inter', system-ui, sans-serif;
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
