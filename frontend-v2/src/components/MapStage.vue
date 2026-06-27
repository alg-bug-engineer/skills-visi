<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CognitionPayload, IntersectionLink, MapActionEvent, MapSceneHud } from '../types/map'
import type { ProblemEvidence, QuantitativeConstraints } from '../types/evidence'
import type { PipelinePhase, HighlightTurn, RuntimeMetrics } from '../types/presentation'
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
import { isEntrance, linkStrokeColor, markerHtml, mergeSceneMarkers, normalizeDir } from '../utils/mapMarkers'
import { buildEvidenceDirectionMarkers, buildProtectedDirectionMarkers, highlightDirsForGroup } from '../utils/evidencePresentation'

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
}>()

const emit = defineEmits<{
  channelizationActive: [active: boolean]
  closeTimingRing: []
  closeCorridorWave: []
  corridorIntersectionSelect: [interId: string]
}>()

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

let map: AMapMap | null = null
let AMapLib: typeof AMap | null = null
let resizeObs: ResizeObserver | null = null
let boxOverlay: InstanceType<typeof AMap.Polygon> | null = null
const linkOverlays: InstanceType<typeof AMap.Polyline>[] = []
const glowOverlays: InstanceType<typeof AMap.Polyline>[] = []
const markers: InstanceType<typeof AMap.Marker>[] = []

const sceneOpts = ref({
  highlightDirs: [] as string[],
  protectedDirs: [] as string[],
  pulseIds: [] as string[],
  flashDirs: [] as string[],
  dimOthers: false,
})

let extraEvidenceMarkers: import('../types/map').MapSceneMarker[] = []

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
  if (!map || !AMapLib || !cognition.value?.intersection) return
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
  if (!map || !AMapLib) return
  clearMarkers()
  const isCorridor = scenePhase.value === 'corridor_scan'
  const selectedId = props.corridorSelectedInterId
  const merged = [...mergeSceneMarkers(action, cognition.value), ...extraEvidenceMarkers].map((m) => {
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
  return props.visualPanOffsetX ?? PANEL_OFFSET_X
}

async function focusCorridorIntersection(lon: number, lat: number, zoom = CORRIDOR_FOCUS_ZOOM) {
  if (!map || !AMapLib || channelizationLocked.value) return
  await flyTo(map, AMapLib, [lon, lat], zoom, 750)
  panToVisualCenter(map, [lon, lat], corridorPanOffsetX(), 0)
}

async function prepareNewAnalysisRun() {
  stopLinkFlash()
  channelizationLocked.value = false
  viewMode.value = 'map'
  hud.value = null
  scenePhase.value = null
  lastCorridorAction = null
  extraEvidenceMarkers = []
  sceneOpts.value = {
    highlightDirs: [],
    protectedDirs: [],
    pulseIds: [],
    flashDirs: [],
    dimOthers: false,
  }
  clearMarkers()
  clearOverlays()
}

async function resetToCityDefault() {
  if (!map || !AMapLib) return
  stopLinkFlash()
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
  await flyTo(map, AMapLib, [lon, lat], 14, 850)
  await flyTo(map, AMapLib, [lon, lat], 16.2, 750)
  await flyTo(map, AMapLib, [lon, lat], 17.5, 650)
  panToVisualCenter(map, [lon, lat], PANEL_OFFSET_X, 0)
}

async function enterChannelizationView(lon: number, lat: number) {
  if (!map || !AMapLib) return
  await flyTo(map, AMapLib, [lon, lat], 18.2, 900)
  stopLinkFlash()
  clearMarkers()
  clearOverlays()
  channelizationLocked.value = true
  viewMode.value = 'channelization'
}

async function focusPoint(lon: number, lat: number, zoom: number) {
  if (!map || !AMapLib || channelizationLocked.value) return
  await flyTo(map, AMapLib, [lon, lat], zoom, 900)
  panToVisualCenter(map, [lon, lat], PANEL_OFFSET_X, 0)
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

  if (!channelizationLocked.value) {
    sceneOpts.value = {
      highlightDirs: action.highlight_dirs ?? [],
      protectedDirs: props.protectedDirs ?? [],
      pulseIds: action.pulse_link_ids ?? [],
      flashDirs: [],
      dimOthers: action.dim_other_links ?? false,
    }
    drawHighlights()
    renderMarkers(action)
  }

  if (channelizationLocked.value) return

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
      break
    }
    case 'update_metrics': {
      if (!cognition.value) return
      cognition.value = {
        ...cognition.value,
        metrics_by_arm: action.metrics_by_arm ?? cognition.value.metrics_by_arm,
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
    await handleAction(props.mapActions[len - 1])
  },
)

watch(
  showChanFull,
  (active) => {
    emit('channelizationActive', active)
  },
  { immediate: true },
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
  drawHighlights()
  renderMarkers({ action: 'map_scene', phase: 'evidence' })
}

onMounted(async () => {
  try {
    AMapLib = await loadAmap()
    if (!mapContainer.value) return
    map = createDarkMap(mapContainer.value, AMapLib)
    ready.value = true

    resizeObs = new ResizeObserver(() => {
      if (cognition.value?.intersection) {
        const inter = cognition.value.intersection
        panToVisualCenter(map!, [inter.lon, inter.lat], PANEL_OFFSET_X, 0)
      }
    })
    resizeObs.observe(mapContainer.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
})

onUnmounted(() => {
  stopLinkFlash()
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
      v-show="viewMode === 'map'"
      ref="mapContainer"
      class="map-canvas"
      :class="{ 'map-fade-out': showChanFull }"
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
      :run-key="props.analysisRunKey ?? 0"
      @close-timing-ring="emit('closeTimingRing')"
      @close-corridor-wave="emit('closeCorridorWave')"
    />

    <Transition name="hud-fade">
      <div v-if="(hudOverride ?? hud) && showChanFull" class="map-hud chan-hud">
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
  background: #1a2030;
}

.map-canvas {
  width: 100%;
  height: 100%;
  transition: opacity 0.5s ease;
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
