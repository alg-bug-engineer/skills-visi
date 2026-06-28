<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import type { CognitionPayload, MapSceneHud, MapSceneMarker } from '../../types/map'
import type {
  HighlightTurn,
  PipelinePhase,
  RuntimeMetrics,
  GovernanceSuggestionPayload,
} from '../../types/presentation'
import type { PresentationLayerGates } from '../../composables/usePresentationSequence'
import { COGNITION_STRUCTURE_PHASES } from '../../types/presentation'
import { useChannelFooterLayout } from '../../composables/useChannelFooterLayout'
import type { FlowTimingGovernance } from '../../types/evidence'
import ChannelizationLegend from './ChannelizationLegend.vue'
import ChannelizationEvidenceNote from './ChannelizationEvidenceNote.vue'
import ChannelizationSuggestionNote from './ChannelizationSuggestionNote.vue'
import TimingRingMiniWindow from '../timing/TimingRingMiniWindow.vue'
import CorridorWaveMiniWindow from '../corridor/CorridorWaveMiniWindow.vue'

const props = defineProps<{
  visible: boolean
  fullscreen?: boolean
  cognition: CognitionPayload | null
  highlightDirs?: string[]
  protectedDirs?: string[]
  evidence?: ProblemEvidence | null
  phase?: PipelinePhase
  highlightTurn?: HighlightTurn | null
  runtimeMetrics?: RuntimeMetrics | null
  timingRingVisible?: boolean
  corridorWaveVisible?: boolean
  showEvidenceNote?: boolean
  showGovernanceNote?: boolean
  governance?: FlowTimingGovernance | null
  governanceSuggestion?: GovernanceSuggestionPayload | null
  sceneMarkers?: MapSceneMarker[]
  hud?: MapSceneHud | null
  /** 新一轮分析时递增，用于重置粘性浮层 */
  runKey?: number
  presentationLayers?: PresentationLayerGates
}>()

const emit = defineEmits<{
  closeTimingRing: []
  closeCorridorWave: []
}>()

const phaseLabel = computed(() => {
  const map: Partial<Record<PipelinePhase, string>> = {
    links: '进口车道',
    channelization: '渠化结构',
    direction: '分向画像',
    granularity: '转向 · 车道',
    saturation: '饱和度',
    imbalance: '失衡',
    traffic: '运行流量',
  }
  return map[props.phase ?? 'links'] ?? '路口渠化'
})

const { queueArms } = useChannelFooterLayout({
  phase: computed(() => props.phase ?? 'idle'),
  cognition: computed(() => props.cognition),
  evidence: computed(() => props.evidence ?? null),
  runtimeMetrics: computed(() => props.runtimeMetrics ?? null),
  fullscreen: computed(() => Boolean(props.fullscreen)),
})

const showDirectionRoles = computed(
  () =>
    props.phase === 'direction' &&
    Boolean(props.highlightDirs?.length || props.protectedDirs?.length),
)

const showHudBar = computed(() => props.presentationLayers?.hudBar ?? true)

const hasQueue = computed(() => {
  if (COGNITION_STRUCTURE_PHASES.includes(props.phase ?? 'idle')) return false
  return queueArms.value.some((a) => a.queueM > 0)
})

const totalLanes = computed(() =>
  (props.cognition?.arms ?? []).reduce(
    (sum, a) => sum + (a.lane_num || a.lanes?.length || 0),
    0,
  ),
)

const evidenceNoteRevealed = ref(false)
const governanceNoteRevealed = ref(false)

const chanBodyRef = ref<HTMLElement | null>(null)
const legendCompRef = ref<InstanceType<typeof ChannelizationLegend> | null>(null)
const evidenceNoteMaxPx = ref<number | null>(null)

const EVIDENCE_NOTE_TOP = 12
const LEGEND_BOTTOM = 12
const EVIDENCE_LEGEND_GAP = 12

function legendEl(): HTMLElement | null {
  const el = legendCompRef.value?.$el
  return el instanceof HTMLElement ? el : null
}

function measureEvidenceNoteMax() {
  const body = chanBodyRef.value
  if (!body) return
  const bodyH = body.clientHeight
  if (bodyH <= 0) return

  const legendH = legendEl()?.offsetHeight ?? 0
  const maxByRatio = bodyH * (2 / 3)
  const maxByLegend =
    bodyH - EVIDENCE_NOTE_TOP - EVIDENCE_LEGEND_GAP - legendH - LEGEND_BOTTOM

  evidenceNoteMaxPx.value = Math.max(96, Math.min(maxByRatio, maxByLegend))
}

const evidenceNoteStyle = computed(() =>
  evidenceNoteMaxPx.value != null
    ? { maxHeight: `${evidenceNoteMaxPx.value}px` }
    : undefined,
)

let resizeObs: ResizeObserver | null = null

function bindResizeObserver() {
  resizeObs?.disconnect()
  resizeObs = new ResizeObserver(() => measureEvidenceNoteMax())
  if (chanBodyRef.value) resizeObs.observe(chanBodyRef.value)
  const legend = legendEl()
  if (legend) resizeObs.observe(legend)
  measureEvidenceNoteMax()
}

onMounted(() => {
  void nextTick(bindResizeObserver)
})

onUnmounted(() => {
  resizeObs?.disconnect()
  resizeObs = null
})

watch(
  () => props.showEvidenceNote,
  (v) => {
    if (v) evidenceNoteRevealed.value = true
  },
  { immediate: true },
)

watch(
  () => props.showGovernanceNote,
  (v) => {
    if (v) governanceNoteRevealed.value = true
  },
  { immediate: true },
)

watch(
  () => props.runKey,
  () => {
    evidenceNoteRevealed.value = false
    governanceNoteRevealed.value = false
  },
)

watch(
  [
    () => props.visible,
    () => props.fullscreen,
    evidenceNoteRevealed,
    hasQueue,
    () => props.phase,
  ],
  () => {
    void nextTick(bindResizeObserver)
  },
)
</script>

<template>
  <Transition :name="fullscreen ? 'chan-full' : 'chan-stage'">
    <div
      v-if="visible && cognition?.arms?.length"
      class="chan-stage"
      :class="{ fullscreen: fullscreen }"
      role="main"
      aria-label="路口渠化视图"
    >
      <header class="chan-head">
        <div>
          <span class="eyebrow">INTERSECTION</span>
          <h3>{{ cognition.intersection.name }}</h3>
          <p v-if="fullscreen" class="meta">
            {{ cognition.arms.length }} 进口 · {{ totalLanes }} 车道
            <span v-if="cognition.intersection.total_lanes">
              （台账 {{ cognition.intersection.total_lanes }}）
            </span>
          </p>
        </div>
        <span class="phase-tag">{{ phaseLabel }}</span>
      </header>

      <div v-if="fullscreen && showHudBar && hud?.metrics?.length" class="chan-hud-bar">
        <div class="chan-hud-head">
          <span v-if="hud.icon" class="hud-icon">{{ hud.icon }}</span>
          <span class="hud-title">{{ hud.title }}</span>
        </div>
        <div class="chan-hud-metrics">
          <div
            v-for="(m, i) in hud.metrics"
            :key="i"
            class="chan-hud-metric"
            :class="`sev-${m.severity || 'unknown'}`"
          >
            <span class="metric-label">{{ m.label }}</span>
            <span class="metric-value">{{ m.value }}</span>
          </div>
        </div>
      </div>

      <div ref="chanBodyRef" class="chan-body">
        <div v-if="fullscreen" class="chan-minis">
          <TimingRingMiniWindow
            :visible="Boolean(timingRingVisible)"
            :profile="evidence?.timing_profile"
            @close="emit('closeTimingRing')"
          />
          <CorridorWaveMiniWindow
            :visible="Boolean(corridorWaveVisible)"
            :corridor="evidence?.corridor_context"
            @close="emit('closeCorridorWave')"
          />
        </div>
        <div
          v-if="fullscreen && evidenceNoteRevealed && evidence"
          class="chan-evidence-note"
          :style="evidenceNoteStyle"
        >
          <ChannelizationEvidenceNote :evidence="evidence" />
        </div>
        <ChannelizationSuggestionNote
          v-if="fullscreen && governanceNoteRevealed"
          class="chan-suggestion-note"
          :suggestion="governanceSuggestion"
        />
        <!-- 渠化已下沉到主地图(AMap 覆盖物)渲染，此处仅留透传区让地图显示，
             图例/证据/建议/迷你窗作为 HUD 浮层叠加 -->
        <div class="chan-map-passthrough" />
        <ChannelizationLegend
          v-if="fullscreen"
          ref="legendCompRef"
          :phase="phase"
          :show-queue="hasQueue"
          :show-direction-roles="showDirectionRoles"
          :run-key="runKey"
        />
      </div>

    </div>
  </Transition>
</template>

<style scoped>
.chan-stage {
  position: absolute;
  inset: 0;
  z-index: 13;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 16px 20px 88px;
}

.chan-stage.fullscreen {
  pointer-events: none;
  flex-direction: column;
  align-items: stretch;
  justify-content: stretch;
  padding: 0;
  background: transparent;
}

.chan-head {
  display: none;
}

.fullscreen .chan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.25);
  flex-shrink: 0;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1.4px;
  color: rgba(180, 195, 210, 0.75);
}

.chan-head h3 {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: #f0f4f8;
}

.meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(180, 195, 210, 0.7);
}

.phase-tag {
  flex-shrink: 0;
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #e8edf5;
  background: rgba(255, 255, 255, 0.06);
}

.chan-hud-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(0, 212, 240, 0.15);
  background: rgba(0, 8, 18, 0.72);
  pointer-events: none;
}

.chan-hud-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.chan-hud-head .hud-icon {
  font-size: 14px;
}

.chan-hud-head .hud-title {
  font-size: 12px;
  font-weight: 600;
  color: rgba(220, 240, 255, 0.95);
}

.chan-hud-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-left: auto;
}

.chan-hud-metric {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 11px;
}

.chan-hud-metric .metric-label {
  color: rgba(180, 200, 220, 0.75);
}

.chan-hud-metric .metric-value {
  color: #00e5ff;
  font-weight: 600;
}

.chan-hud-metric.sev-high .metric-value {
  color: #ff8a80;
}

.chan-hud-metric.sev-medium .metric-value {
  color: #ffcc66;
}

.chan-body {
  flex: 1;
  min-height: 0;
  position: relative;
}

/* 渠化下沉主图后的透传占位：撑开布局让图例落到底部，并放行地图交互 */
.chan-map-passthrough {
  flex: 1 1 auto;
  min-height: 0;
  pointer-events: none;
}

.fullscreen .chan-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
}

.chan-minis {
  position: absolute;
  top: 8px;
  left: 0;
  right: 0;
  z-index: 5;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 0 12px;
  pointer-events: none;
}

.chan-minis :deep(.timing-mini),
.chan-minis :deep(.corridor-mini) {
  position: relative;
  top: auto;
  left: auto;
  right: auto;
  bottom: auto;
  transform: none;
  pointer-events: auto;
}

.chan-evidence-note {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 6;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  pointer-events: auto;
}

.chan-evidence-note :deep(.evidence-note) {
  flex: 1 1 auto;
  min-height: 0;
  max-height: 100%;
  overflow-y: auto;
}

.chan-suggestion-note {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 6;
}

.chan-full-enter-active,
.chan-full-leave-active {
  transition: opacity 0.55s ease, transform 0.55s ease;
}

.chan-full-enter-from,
.chan-full-leave-to {
  opacity: 0;
  transform: scale(1.04);
}

</style>
