<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import type { CognitionPayload } from '../../types/map'
import type {
  HighlightTurn,
  PipelinePhase,
  RuntimeMetrics,
  GovernanceSuggestionPayload,
} from '../../types/presentation'
import { COGNITION_STRUCTURE_PHASES } from '../../types/presentation'
import { useChannelFooterLayout } from '../../composables/useChannelFooterLayout'
import type { FlowTimingGovernance } from '../../types/evidence'
import ChannelizationCanvas3D from './ChannelizationCanvas3D.vue'
import ChannelizationLegend from './ChannelizationLegend.vue'
import ChannelizationMetricStrip from './ChannelizationMetricStrip.vue'
import ChannelizationImbalanceBanner from './ChannelizationImbalanceBanner.vue'
import ChannelizationEvidenceNote from './ChannelizationEvidenceNote.vue'
import ChannelizationSuggestionNote from './ChannelizationSuggestionNote.vue'
import TimingRingMiniWindow from '../timing/TimingRingMiniWindow.vue'
import CorridorWaveMiniWindow from '../corridor/CorridorWaveMiniWindow.vue'

const props = defineProps<{
  visible: boolean
  fullscreen?: boolean
  cognition: CognitionPayload | null
  highlightDirs?: string[]
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
  /** 新一轮分析时递增，用于重置粘性浮层 */
  runKey?: number
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

const {
  queueArms,
  showMetricStrip,
  showImbalanceBanner,
  imbalance,
} = useChannelFooterLayout({
  phase: computed(() => props.phase ?? 'idle'),
  cognition: computed(() => props.cognition),
  evidence: computed(() => props.evidence ?? null),
  runtimeMetrics: computed(() => props.runtimeMetrics ?? null),
  fullscreen: computed(() => Boolean(props.fullscreen)),
  runKey: computed(() => props.runKey ?? 0),
})

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

      <div class="chan-body">
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
        <ChannelizationEvidenceNote
          v-if="fullscreen && evidenceNoteRevealed && evidence"
          class="chan-evidence-note"
          :evidence="evidence"
        />
        <ChannelizationSuggestionNote
          v-if="fullscreen && governanceNoteRevealed"
          class="chan-suggestion-note"
          :suggestion="governanceSuggestion"
        />
        <ChannelizationCanvas3D
          :cognition="cognition"
          :evidence="evidence"
          :phase="phase"
          :highlight-dirs="highlightDirs"
          :highlight-turn="highlightTurn"
          :runtime-metrics="runtimeMetrics"
        />
        <ChannelizationLegend
          v-if="fullscreen"
          :phase="phase"
          :show-queue="hasQueue"
          :run-key="runKey"
        />
      </div>

      <Transition name="chan-footer-rise">
        <div v-if="showImbalanceBanner" key="imbalance-banner" class="chan-imbalance-row">
          <ChannelizationImbalanceBanner :value="imbalance!" />
        </div>
      </Transition>

      <Transition name="chan-footer-rise">
        <ChannelizationMetricStrip
          v-if="showMetricStrip"
          key="metric-strip"
          :queue-arms="queueArms"
        />
      </Transition>
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
  pointer-events: auto;
  flex-direction: column;
  align-items: stretch;
  justify-content: stretch;
  padding: 0;
  background: #1a2030;
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

.chan-body {
  flex: 1;
  min-height: 0;
  position: relative;
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
}

.chan-suggestion-note {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 6;
}

.chan-imbalance-row {
  flex-shrink: 0;
  padding: 6px 12px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.22);
}

.chan-imbalance-row :deep(.imbalance-banner) {
  max-width: calc(100% - 300px);
}

@media (max-width: 900px) {
  .chan-imbalance-row :deep(.imbalance-banner) {
    max-width: 100%;
  }
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

.chan-footer-rise-enter-active {
  transition:
    transform 0.42s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.32s ease;
}

.chan-footer-rise-leave-active {
  transition: none;
}

.chan-footer-rise-enter-from,
.chan-footer-rise-leave-to {
  opacity: 0;
  transform: translateY(18px);
}

.chan-footer-rise-enter-to,
.chan-footer-rise-leave-from {
  opacity: 1;
  transform: translateY(0);
}
</style>
