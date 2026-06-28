<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import type { CognitionPayload, MapSceneMarker } from '../../types/map'
import type { ProblemEvidence } from '../../types/evidence'
import type { HighlightTurn, PipelinePhase, RuntimeMetrics } from '../../types/presentation'
import { COGNITION_STRUCTURE_PHASES } from '../../types/presentation'
import {
  createChannelizationLayer,
  disposeChannelizationLayer,
  getChannelizationView,
  applyCheckHighlight,
  applyTurnHighlight,
  applyDirectionRoleHighlight,
  applyArmSceneLabels,
  clearCheckHighlight,
} from '../../lib/channelizationLayer.js'
import {
  buildHighlightEvidence,
  buildInterItemFromCognition,
  buildQueueDataFromEvidence,
  highlightVerdict,
  turnCodeFromLabel,
} from '../../utils/cognitionChannelAdapter'
import { buildArmLabelsFromScene } from '../../utils/channelArmLabels'
import { highlightDirsForGroup } from '../../utils/evidencePresentation'

const props = defineProps<{
  cognition: CognitionPayload | null
  evidence?: ProblemEvidence | null
  phase?: PipelinePhase
  highlightDirs?: string[]
  protectedDirs?: string[]
  highlightTurn?: HighlightTurn | null
  runtimeMetrics?: RuntimeMetrics | null
  sceneMarkers?: MapSceneMarker[]
}>()

const hostRef = ref<HTMLDivElement | null>(null)

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let channelGroup: THREE.Group | null = null
let resizeObs: ResizeObserver | null = null
let rafId = 0

function applyPhaseHighlight() {
  if (!channelGroup) return
  clearCheckHighlight(channelGroup)

  const phase = props.phase ?? 'idle'
  const isStructurePhase = COGNITION_STRUCTURE_PHASES.includes(phase)

  if (props.highlightTurn && !isStructurePhase) {
    applyTurnHighlight(channelGroup, {
      dir: props.highlightTurn.dir,
      turnCode: turnCodeFromLabel(props.highlightTurn.turn),
      label: props.highlightTurn.label ?? `${props.highlightTurn.dir}${props.highlightTurn.turn}`,
      saturation: props.highlightTurn.saturation ?? undefined,
    })
    return
  }

  const ev = buildHighlightEvidence(
    props.cognition,
    props.evidence ?? null,
    props.runtimeMetrics ?? null,
  )

  if (isStructurePhase) return

  if (phase === 'saturation') {
    const sat = ev.saturation_max ?? null
    if (sat == null) return
    applyCheckHighlight(
      channelGroup,
      'saturation',
      highlightVerdict(sat, 0.85, 0.65),
      ev,
    )
  } else if (phase === 'traffic') {
    // 流量阶段不叠加饱和度浮标，避免与 saturation 阶段重复
  } else if (phase === 'imbalance') {
    const imb = ev.unbalance_index ?? null
    if (imb == null) return
    applyCheckHighlight(
      channelGroup,
      'imbalance',
      highlightVerdict(imb, 0.35, 0.25),
      ev,
    )
  } else if (phase === 'granularity') {
    const sat = ev.max_turn_saturation ?? ev.saturation_max ?? null
    if (sat == null) return
    applyCheckHighlight(channelGroup, 'saturation', highlightVerdict(sat, 0.85, 0.65), ev)
  }

  applyDirectionRoleHighlightOnArms()
  applyArmSceneLabels(
    channelGroup,
    buildArmLabelsFromScene(props.sceneMarkers ?? [], props.cognition),
  )
}

function protectDirKeys(): string[] {
  return (props.protectedDirs ?? []).flatMap((group) => highlightDirsForGroup(group))
}

function applyDirectionRoleHighlightOnArms() {
  if (!channelGroup) return
  const focus = props.highlightDirs ?? []
  const protect = protectDirKeys()
  if (!focus.length && !protect.length) {
    applyDirectionRoleHighlight(channelGroup, [], [])
    return
  }
  applyDirectionRoleHighlight(channelGroup, focus, protect)
}

function fitCamera() {
  if (!camera || !channelGroup || !hostRef.value) return
  const view = getChannelizationView(channelGroup)
  const { center, height } = view
  camera.position.set(center.x, height, center.z + 0.01)
  camera.lookAt(center)
  camera.updateProjectionMatrix()
}

function rebuild() {
  if (!scene || !props.cognition?.arms?.length) return

  if (channelGroup) {
    disposeChannelizationLayer(channelGroup)
    scene.remove(channelGroup)
    channelGroup = null
  }

  const interItem = buildInterItemFromCognition(props.cognition)
  const phase = props.phase ?? 'idle'
  const queueData = COGNITION_STRUCTURE_PHASES.includes(phase)
    ? []
    : buildQueueDataFromEvidence(
        props.cognition,
        props.evidence ?? null,
        props.runtimeMetrics ?? null,
      )

  channelGroup = createChannelizationLayer(interItem, queueData, { centerAtOrigin: true })
  scene.add(channelGroup)
  applyPhaseHighlight()
  fitCamera()
}

function renderFrame() {
  if (!renderer || !scene || !camera) return
  renderer.render(scene, camera)
}

function resize() {
  const host = hostRef.value
  if (!host || !renderer || !camera) return
  const w = host.clientWidth
  const h = host.clientHeight
  if (w < 1 || h < 1) return
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  fitCamera()
  renderFrame()
}

function initThree() {
  const host = hostRef.value
  if (!host) return

  scene = new THREE.Scene()
  scene.background = null

  const w = host.clientWidth || 800
  const h = host.clientHeight || 600
  camera = new THREE.PerspectiveCamera(42, w / h, 0.5, 2000)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h, false)
  host.appendChild(renderer.domElement)

  const ambient = new THREE.AmbientLight(0xffffff, 0.95)
  scene.add(ambient)

  rebuild()
  renderFrame()
}

function disposeThree() {
  cancelAnimationFrame(rafId)
  if (channelGroup && scene) {
    disposeChannelizationLayer(channelGroup)
    scene.remove(channelGroup)
  }
  channelGroup = null
  renderer?.dispose()
  renderer?.domElement.remove()
  renderer = null
  scene = null
  camera = null
}

onMounted(() => {
  initThree()
  if (hostRef.value) {
    resizeObs = new ResizeObserver(() => resize())
    resizeObs.observe(hostRef.value)
  }
})

onUnmounted(() => {
  resizeObs?.disconnect()
  disposeThree()
})

watch(
  () => [
    props.cognition,
    props.evidence,
    props.phase,
    props.highlightDirs,
    props.protectedDirs,
    props.highlightTurn,
    props.runtimeMetrics,
    props.sceneMarkers,
  ],
  () => {
    rebuild()
    renderFrame()
  },
  { deep: true },
)
</script>

<template>
  <div ref="hostRef" class="chan-canvas-3d" />
</template>

<style scoped>
.chan-canvas-3d {
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.chan-canvas-3d :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
</style>
