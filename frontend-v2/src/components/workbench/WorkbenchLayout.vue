<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PresentationState } from '../../types/presentation'
import { shouldShowCorridorWaveMini, shouldShowTimingRingMini } from '../../types/presentation'
import type { MapActionEvent } from '../../types/map'
import InputDock from '../InputDock.vue'
import MapStage from '../MapStage.vue'
import IntersectionNarrativeStack from '../channelization/IntersectionNarrativeStack.vue'
import CorridorScanSidebar from '../corridor/CorridorScanSidebar.vue'
import VoiceToggle from '../VoiceToggle.vue'
import UnderstandingProcessPanel, {
  type ConversationTurn,
} from '../UnderstandingProcessPanel.vue'
import SkillBuildDrawer from '../SkillBuildDrawer.vue'
import type { ProcessStepState } from '../../composables/useUnderstandingProcess'
import type { SkillBuildState } from '../../types/skillBuild'
import type { PresentationLayerGates } from '../../composables/usePresentationSequence'

const props = defineProps<{
  presentation: PresentationState
  mapActions: MapActionEvent[]
  processSteps: ProcessStepState[]
  panelMode: 'idle' | 'conversation' | 'analysis'
  conversation: ConversationTurn[]
  missingFields: string[]
  processActive: boolean
  docked: boolean
  inputLocked: boolean
  analysisTerminal?: boolean
  loading: boolean
  followUpBubble: string | null
  mapToast: string | null
  showConfirm: boolean
  confirmMessage: string
  errorBanner: string | null
  hideInputDock?: boolean
  channelizationActive?: boolean
  analysisRunKey?: number
  panelLayout?: 'single' | 'stacked'
  skillBuildState?: SkillBuildState
  voiceEnabled?: boolean
  voicePlaying?: boolean
  presentationPaused?: boolean
  /** 治理建议二次确认引导条；与空格演示暂停互斥展示 */
  suggestionConfirmBanner?: string | null
  presentationLayers?: PresentationLayerGates
  focusStepIndex?: number
  /** 路口结构步骤完成且运行数据面板已揭示后，才允许地图/左侧运行指标 */
  runtimeMetricsUnlocked?: boolean
  leaderboardRefreshKey?: number
}>()

const emit = defineEmits<{
  send: [content: string]
  inputActivity: [value: string]
  toggleStep: [index: number]
  toggleDetails: [index: number]
  toggleProcess: []
  toggleTimingRing: []
  closeTimingRing: []
  toggleCorridorWave: []
  closeCorridorWave: []
  toggleVoice: []
  confirm: []
  deny: []
  returnHome: []
  channelizationActive: [active: boolean]
  selectSkillFile: [path: string]
  skillBuildFinish: []
  corridorSelect: [interId: string]
  upstreamNarration: [payload: { idx: number; text: string | null }]
}>()

const mapStageRef = ref<InstanceType<typeof MapStage> | null>(null)

defineExpose({ mapStageRef })

const showNarrativeStack = computed(
  () =>
    Boolean(props.presentation.cognition?.intersection) &&
    props.presentation.phase !== 'corridor_scan' &&
    props.presentation.phase !== 'idle',
)

/** 技能写入终端展开时隐藏左侧路口态势面板，避免与终端重叠 */
const hideLeftNarrative = computed(
  () => Boolean(props.skillBuildState?.visible && !props.skillBuildState?.exiting),
)

const showTimingMini = computed(() => {
  const layers = props.presentationLayers
  const autoOk = layers ? layers.timingRingAuto : true
  return autoOk && shouldShowTimingRingMini(props.presentation.phase, props.presentation)
})

const showCorridorSidebar = computed(
  () => props.presentation.phase === 'corridor_scan' && Boolean(props.presentation.corridorScan),
)

const corridorPanOffsetX = computed(() => (showCorridorSidebar.value ? 90 : -120))

const showCorridorMini = computed(() => {
  const layers = props.presentationLayers
  const autoOk = layers ? layers.corridorWaveAuto : true
  return autoOk && shouldShowCorridorWaveMini(props.presentation.phase, props.presentation)
})

const showEvidenceOnMap = computed(
  () =>
    props.presentation.revealedInsightSteps.evidence &&
    (props.presentationLayers?.evidenceNote ?? true),
)

const canToggleTiming = computed(
  () => Boolean(props.presentation.evidence?.timing_profile?.ring_diagram?.available),
)

const canToggleCorridor = computed(
  () =>
    Boolean(props.presentation.evidence?.corridor_context?.in_corridor) ||
    (props.presentation.evidence?.corridor_context?.corridor_nodes?.length ?? 0) > 0,
)

</script>

<template>
  <div class="workbench">
    <div v-if="errorBanner" class="error-banner">{{ errorBanner }}</div>

    <div
      class="workbench-grid"
      :class="{
        'process-collapsed': presentation.processCollapsed,
        'corridor-active': showCorridorSidebar,
      }"
    >
      <CorridorScanSidebar
        v-if="showCorridorSidebar && presentation.corridorScan"
        class="corridor-column"
        :corridor="presentation.corridorScan"
        @select="emit('corridorSelect', $event)"
      />

      <main class="stage-column">
        <div class="stage-toolbar">
          <span class="stage-label">路口 GIS</span>
          <div class="toolbar-actions">
            <button
              v-if="canToggleTiming"
              type="button"
              class="chan-toggle timing"
              :class="{ active: showTimingMini }"
              @click="emit('toggleTimingRing')"
            >
              配时环图
            </button>
          </div>
        </div>

        <div class="stage-body">
          <VoiceToggle
            class="stage-voice-toggle"
            :enabled="Boolean(voiceEnabled)"
            :playing="Boolean(voicePlaying)"
            @toggle="emit('toggleVoice')"
          />

          <SkillBuildDrawer
            v-if="skillBuildState"
            :state="skillBuildState"
            @select-file="emit('selectSkillFile', $event)"
            @finish="emit('skillBuildFinish')"
          />

          <MapStage
            ref="mapStageRef"
            :map-actions="mapActions"
            :highlight-dirs="presentation.highlightDirs"
            :protected-dirs="presentation.protectedDirs"
            :focused-dirs="presentation.focusedDirs"
            :hud-override="presentation.hud"
            :cognition="presentation.cognition"
            :pipeline-phase="presentation.phase"
            :evidence="presentation.evidence"
            :highlight-turn="presentation.highlightTurn"
            :runtime-metrics="presentation.runtimeMetrics"
            :timing-ring-visible="showTimingMini"
            :corridor-wave-visible="false"
            :show-evidence-note="showEvidenceOnMap"
            :presentation-layers="presentationLayers ?? undefined"
            :show-governance-note="presentation.revealedInsightSteps.suggestionNote"
            :governance="presentation.flowTimingGovernance"
            :governance-suggestion="presentation.governanceSuggestion"
            :analysis-run-key="analysisRunKey"
            :corridor-selected-inter-id="presentation.corridorScan?.selectedInterId ?? null"
            :visual-pan-offset-x="corridorPanOffsetX"
            :suppress-stage-hud="showNarrativeStack"
            :active-dimensions="presentation.activeDimensions"
            :runtime-panel-revealed="runtimeMetricsUnlocked"
            :focus-step-index="focusStepIndex"
            @channelization-active="emit('channelizationActive', $event)"
            @close-timing-ring="emit('closeTimingRing')"
            @close-corridor-wave="emit('closeCorridorWave')"
            @corridor-intersection-select="emit('corridorSelect', $event)"
            @upstream-narration="emit('upstreamNarration', $event)"
          />

          <IntersectionNarrativeStack
            :visible="showNarrativeStack"
            :hide-left-panel="hideLeftNarrative"
            :cognition="presentation.cognition"
            :highlight-dirs="presentation.highlightDirs"
            :protected-dirs="presentation.protectedDirs"
            :runtime-metrics="presentation.runtimeMetrics"
            :data-insight="presentation.dataInsightBuffer"
            :evidence="presentation.evidence"
            :governance-suggestion="presentation.governanceSuggestion"
            :flow-timing-governance="presentation.flowTimingGovernance"
            :reused-experience="presentation.reusedExperience"
            :case-experience="presentation.caseExperience"
            :experience-sediment="presentation.experienceSediment"
            :focus-step-index="focusStepIndex ?? -1"
            :runtime-panel-revealed="runtimeMetricsUnlocked"
            :phase="presentation.phase"
            :run-key="analysisRunKey ?? 0"
          />
        </div>

        <Transition name="toast-fade">
          <div
            v-if="presentationPaused && !suggestionConfirmBanner"
            class="pause-toast"
            data-testid="presentation-pause"
          >
            分析暂停 · 空格继续
          </div>
        </Transition>

        <Transition name="toast-fade">
          <div
            v-if="suggestionConfirmBanner"
            class="confirm-prompt-toast"
            data-testid="suggestion-confirm-banner"
          >
            {{ suggestionConfirmBanner }}
          </div>
        </Transition>

        <Transition name="toast-fade">
          <div v-if="mapToast" class="map-toast">{{ mapToast }}</div>
        </Transition>

        <div v-if="showConfirm" class="confirm-bubble">
          <p>{{ confirmMessage }}</p>
          <div class="confirm-actions">
            <button type="button" class="btn-yes" data-testid="confirm-yes" @click="emit('confirm')">
              确认固化
            </button>
            <button type="button" class="btn-no" data-testid="confirm-no" @click="emit('deny')">
              暂不固化
            </button>
          </div>
        </div>

        <InputDock
          v-show="!hideInputDock"
          :docked="docked"
          :locked="inputLocked"
          :terminal="analysisTerminal"
          :loading="loading"
          :conversation="panelMode === 'conversation'"
          :awaiting-suggestion-confirm="Boolean(suggestionConfirmBanner)"
          @send="emit('send', $event)"
          @input-activity="emit('inputActivity', $event)"
          @return-home="emit('returnHome')"
        />
      </main>

      <aside v-show="!presentation.processCollapsed" class="process-column" :class="{ stacked: panelLayout === 'stacked' }">
        <UnderstandingProcessPanel
          class="process-panel process-panel-top"
          embedded
          :steps="processSteps"
          :mode="panelMode"
          :conversation="conversation"
          :missing-fields="missingFields"
          :active="processActive"
          :stack-summary-mode="panelLayout === 'stacked'"
          :leaderboard-refresh-key="leaderboardRefreshKey"
          @toggle="emit('toggleStep', $event)"
          @toggle-details="emit('toggleDetails', $event)"
        />
      </aside>
    </div>

    <button
      type="button"
      class="process-fab"
      :title="presentation.processCollapsed ? '展开理解过程' : '收起理解过程'"
      @click="emit('toggleProcess')"
    >
      {{ presentation.processCollapsed ? '过程' : '收起' }}
    </button>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #020810;
  position: relative;
}

.error-banner {
  padding: 10px 16px;
  background: rgba(200, 50, 40, 0.25);
  color: #ffb4b4;
  font-size: 13px;
  border-bottom: 1px solid rgba(255, 100, 80, 0.25);
  flex-shrink: 0;
}

.workbench-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr minmax(300px, 360px);
}

.workbench-grid.corridor-active {
  grid-template-columns: minmax(240px, 280px) 1fr minmax(300px, 360px);
}

.workbench-grid.corridor-active.process-collapsed {
  grid-template-columns: minmax(240px, 280px) 1fr;
}

.corridor-column {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.workbench-grid.process-collapsed {
  grid-template-columns: 1fr;
}

.stage-column {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.stage-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(0, 212, 240, 0.12);
  background: rgba(0, 8, 16, 0.92);
  flex-shrink: 0;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.stage-label {
  font-size: 11px;
  letter-spacing: 0.5px;
  color: rgba(0, 229, 255, 0.75);
}

.chan-toggle {
  padding: 4px 10px;
  font-size: 11px;
  border: 1px solid rgba(0, 212, 240, 0.25);
  background: transparent;
  color: rgba(200, 230, 255, 0.55);
  border-radius: 2px;
  cursor: pointer;
}

.chan-toggle.active {
  color: #00e5ff;
  border-color: rgba(0, 212, 240, 0.5);
  background: rgba(0, 212, 240, 0.1);
}

.chan-toggle.timing.active {
  color: #ff8a80;
  border-color: rgba(255, 138, 128, 0.45);
  background: rgba(198, 40, 40, 0.12);
}

.chan-toggle.corridor.active {
  color: #69f0ae;
  border-color: rgba(0, 230, 118, 0.35);
  background: rgba(0, 200, 83, 0.1);
}

.stage-body {
  flex: 1;
  min-height: 0;
  position: relative;
}

.stage-voice-toggle {
  position: absolute;
  left: 16px;
  bottom: 24px;
  z-index: 18;
}

.process-column {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid rgba(0, 212, 240, 0.12);
  background: rgba(0, 6, 14, 0.97);
}

.process-column.stacked {
  display: flex;
  flex-direction: column;
}

.process-column.stacked :deep(.process-panel-top.embedded) {
  flex: 0 0 auto;
  max-height: 38%;
  overflow-y: auto;
}

.process-column :deep(.process-panel.embedded) {
  flex: 1;
  min-height: 0;
  height: auto;
  overflow-y: auto;
}

.process-fab {
  position: fixed;
  right: 12px;
  bottom: 88px;
  z-index: 30;
  padding: 8px 12px;
  border-radius: 2px;
  border: 1px solid rgba(0, 212, 240, 0.35);
  background: rgba(0, 12, 24, 0.92);
  color: #00e5ff;
  font-size: 11px;
  cursor: pointer;
}

.map-toast,
.pause-toast,
.confirm-prompt-toast,
.follow-up-bubble,
.confirm-bubble {
  position: absolute;
  z-index: 14;
  left: 50%;
  transform: translateX(-50%);
}

.pause-toast {
  top: 16px;
  padding: 8px 14px;
  background: rgba(20, 24, 32, 0.92);
  border: 1px solid rgba(255, 180, 80, 0.55);
  color: rgba(255, 230, 200, 0.96);
  font-size: 12px;
  letter-spacing: 0.4px;
  pointer-events: none;
}

.confirm-prompt-toast {
  top: 16px;
  max-width: min(560px, 92%);
  padding: 10px 16px;
  background: rgba(0, 14, 28, 0.94);
  border: 1px solid rgba(0, 212, 240, 0.5);
  color: rgba(226, 246, 255, 0.96);
  font-size: 13px;
  line-height: 1.5;
  letter-spacing: 0.2px;
  text-align: center;
  pointer-events: none;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}

.map-toast {
  top: 48px;
  max-width: min(520px, 90%);
  padding: 10px 14px;
  background: rgba(0, 14, 28, 0.92);
  border: 1px solid rgba(0, 212, 240, 0.42);
  color: rgba(226, 246, 255, 0.96);
  font-size: 13px;
  pointer-events: none;
}

.follow-up-bubble {
  top: 50%;
  transform: translate(-50%, -50%);
  max-width: min(420px, 90%);
  padding: 16px 18px;
  background: rgba(0, 12, 24, 0.94);
  border: 1px solid rgba(255, 180, 60, 0.45);
  border-left: 2px solid #ffc266;
}

.follow-up-tag {
  display: inline-block;
  margin-bottom: 8px;
  padding: 2px 8px;
  font-size: 10px;
  color: #ffc266;
}

.follow-up-bubble p {
  margin: 0;
  color: rgba(220, 240, 255, 0.92);
  font-size: 13px;
  line-height: 1.6;
}

.confirm-bubble {
  bottom: 108px;
  padding: 16px 18px;
  background: rgba(0, 12, 24, 0.96);
  border: 1px solid rgba(0, 212, 240, 0.45);
  text-align: center;
  min-width: 280px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55);
}

.confirm-bubble p {
  margin: 0 0 12px;
  color: rgba(220, 240, 255, 0.95);
  font-size: 13px;
  line-height: 1.55;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.btn-yes,
.btn-no {
  padding: 8px 16px;
  border-radius: 2px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
}

.btn-yes {
  background: rgba(0, 212, 240, 0.22);
  color: #00e5ff;
  border: 1px solid rgba(0, 229, 255, 0.55);
}

.btn-yes:hover {
  background: rgba(0, 212, 240, 0.32);
}

.btn-no {
  background: rgba(40, 48, 62, 0.95);
  color: rgba(220, 240, 255, 0.88);
  border: 1px solid rgba(180, 200, 220, 0.45);
}

.btn-no:hover {
  background: rgba(55, 65, 80, 0.98);
  color: #f0f8ff;
  border-color: rgba(200, 220, 240, 0.55);
}

.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity 0.25s ease;
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
}

@media (max-width: 1100px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .process-column {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: min(340px, 88vw);
    z-index: 25;
    box-shadow: -8px 0 32px rgba(0, 0, 0, 0.55);
  }

  .workbench-grid.process-collapsed .process-column {
    display: none;
  }
}
</style>
