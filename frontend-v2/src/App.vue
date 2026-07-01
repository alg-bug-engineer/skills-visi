<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { checkHealth, createSession, sendMessageStream } from './api/client'
import WorkbenchLayout from './components/workbench/WorkbenchLayout.vue'
import {
  STEP_INDICES,
  STEP_PAUSE_MS,
  DATA_FETCH_STEP_PAUSE_MS,
  RUNTIME_PRESENTATION_DELAY_MS,
  SUGGESTION_CONFIRM_BANNER,
} from './constants'
import { shouldRevealRuntimePanel } from './utils/runtimePanelGate'
import {
  isSkillPresentationActive,
  shouldEnterAnalysisTerminal,
  shouldShowSkillSolidificationStep,
} from './utils/regressionSkillFlow'
import { waitForGovernanceSuggestionPresented } from './utils/waitForGovernanceSuggestionPresented'
import {
  frameYield,
  isSkillStreamBufferedEvent,
  shouldEnqueueAbsorptionPauseGate,
  shouldEnqueueSkillBuildPauseGate,
  type SkillBufferedEvent,
} from './utils/skillPresentationDispatch'
import { usePresentation } from './composables/usePresentation'
import { usePresentationPause } from './composables/usePresentationPause'
import { usePresentationSequence } from './composables/usePresentationSequence'
import { createPresentationBarrier } from './composables/usePresentationBarrier'
import { useUnderstandingProcess } from './composables/useUnderstandingProcess'
import { useSkillBuildProcess } from './composables/useSkillBuildProcess'
import { useExperienceAbsorption } from './composables/useExperienceAbsorption'
import { useAbsorptionToasts } from './composables/useAbsorptionToasts'
import ExperienceAbsorptionToast from './components/ExperienceAbsorptionToast.vue'
import { useVoiceNarration } from './composables/useVoiceNarration'
import { SKILL_BUILD_STAGES } from './types/skillBuild'
import type { ChatMessage, MessageResponse, StepRecord } from './types/api'
import type { ProblemEvidence, QuantitativeConstraints } from './types/evidence'
import type { CognitionPayload, IntersectionLink, MapActionEvent } from './types/map'
import type { CorridorIntersectionItem } from './types/corridor'
import type { GovernanceSuggestionPayload, PipelinePhase } from './types/presentation'
import { AnalysisQueue } from './utils/analysisQueue'
import { parseHighlightTurn } from './utils/cognitionChannelAdapter'
import { buildEvidenceListItems, buildSuggestionPlainText, hasSuggestionCardContent } from './utils/channelizationCopy'
import { VOICE_GUIDE } from './services/voiceCueTemplates'
import { processStepPhase, resolveProcessStepVoice } from './services/voiceStepSync'
import {
  buildCognitionVoiceCue,
  buildDirectionVoiceCue,
  buildEvidenceIntroCue,
  buildImbalanceCue,
  buildNarrationPhaseVoiceCue,
  buildRuleCue,
  type DirectionRoleRow,
} from './services/voiceCueExtractors'
import { ABSORPTION_STAGE_VOICE } from './types/voice'
import {
  formatIntersectionMatchSummary,
  formatLocatedIntersectionSummary,
  formatSkillReuseLines,
} from './config/presentationCopy'
import { voiceConfig, voiceTemplate } from './services/voiceConfig'
import { buildUpstreamProcessText } from './utils/upstreamProcessText'
import { upstreamStoryboardDurationMs } from './utils/upstreamTiming'
import type { ConversationTurn } from './components/UnderstandingProcessPanel.vue'
import type MapStage from './components/MapStage.vue'

const presentation = usePresentation()

const sessionId = ref<string | null>(null)
const messages = ref<ChatMessage[]>([])
const steps = ref<StepRecord[]>([])
const loading = ref(false)
const errorBanner = ref<string | null>(null)

const docked = ref(false)
const inputLocked = ref(false)
const analysisTerminalMode = ref(false)
const mapActions = ref<MapActionEvent[]>([])
const showConfirm = ref(false)
const confirmMessage = ref('是否将此诊断固化为路口 Skill？')
const pendingConfirm = ref(false)
const pendingSkillCreateConfirm = ref(false)
let skillSolidificationPresenting = false
const mapToast = ref<string | null>(null)
const awaitingSuggestionConfirm = ref(false)
const suggestionConfirmBanner = computed(() =>
  awaitingSuggestionConfirm.value ? SUGGESTION_CONFIRM_BANNER : null,
)
const channelizationActive = ref(false)
const analysisRunKey = ref(0)
const leaderboardRefreshKey = ref(0)

const mapStageRef = ref<InstanceType<typeof MapStage> | null>(null)
const workbenchRef = ref<InstanceType<typeof WorkbenchLayout> | null>(null)

const PAIRED_NARRATION_PHASES = new Set([
  'traffic',
  'direction',
  'timing',
  'imbalance',
  'rule',
  'conclusion',
])

const DATA_FETCH_MAP_PHASES = new Set([
  'traffic',
  'direction',
  'granularity',
  'timing',
  'external',
  'saturation',
  'imbalance',
])

function resolveMapActionPauseMs(action: MapActionEvent): number {
  if (action.action === 'update_metrics') return DATA_FETCH_STEP_PAUSE_MS
  if (action.phase && DATA_FETCH_MAP_PHASES.has(action.phase)) {
    return DATA_FETCH_STEP_PAUSE_MS
  }
  return STEP_PAUSE_MS
}
let pendingNarration: MapActionEvent | null = null
let lastUserContent = ''

type PanelMode = 'idle' | 'conversation' | 'analysis'
const panelMode = ref<PanelMode>('idle')
const sessionState = ref<string>('idle')
const conversationTurns = ref<ConversationTurn[]>([])
const missingFields = ref<string[]>([])
const followUpBubble = ref<string | null>(null)

const voice = useVoiceNarration()
const analysisQueue = new AnalysisQueue()
const presentationPause = usePresentationPause(analysisQueue, voice)
const presentationSequence = usePresentationSequence()
const lastIntersectionName = ref<string | null>(null)
const voiceSentForStep = new Set<number>()
let dataFetchGuideQueued = false
let pendingPresentationStepIndex: number | null = null
let runtimeRevealTimer: ReturnType<typeof setTimeout> | null = null
let pendingRuleEngineVoice: Record<string, unknown> | null = null

function isCognitionStepDone(): boolean {
  const cog = processSteps.value.find((s) => s.index === STEP_INDICES.COGNITION)
  return cog?.status === 'done'
}

const runtimeMetricsUnlocked = computed(() => {
  if (!presentation.state.revealedInsightSteps.runtimePanel) return false
  return isCognitionStepDone()
})

function clearRuntimeRevealTimer() {
  if (runtimeRevealTimer) {
    clearTimeout(runtimeRevealTimer)
    runtimeRevealTimer = null
  }
}

/** 运行数据面板：路口结构完成 + 进入运行数据步骤后，再延时揭示（避免与旁白抢拍）。 */
function scheduleRevealRuntimePanel() {
  const dataFetchStarted = processSteps.value.some((s) => s.index === STEP_INDICES.DATA_FETCH)
  if (!shouldRevealRuntimePanel(dataFetchStarted, isCognitionStepDone())) return
  if (presentation.state.revealedInsightSteps.runtimePanel) return
  clearRuntimeRevealTimer()
  runtimeRevealTimer = setTimeout(() => {
    runtimeRevealTimer = null
    const started = processSteps.value.some((s) => s.index === STEP_INDICES.DATA_FETCH)
    if (!shouldRevealRuntimePanel(started, isCognitionStepDone())) return
    presentation.revealRuntimePanel()
  }, RUNTIME_PRESENTATION_DELAY_MS)
}

function flushDeferredPresentationStep() {
  if (pendingPresentationStepIndex == null) return
  if (!isCognitionStepDone()) return
  presentationSequence.syncFromStepIndex(pendingPresentationStepIndex)
  pendingPresentationStepIndex = null
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isDataFetchSubBeat(phase?: string | null): boolean {
  return Boolean(phase && ['traffic', 'direction', 'timing', 'imbalance'].includes(phase))
}

/** 流量溯源逐帧旁白仅驱动地图，不再追加 TTS（入口一句 upstreamIntro 即可）。 */
function handleUpstreamNarration(_payload: { idx: number; text: string | null }) {
  return
}

/** 流量溯源概要讲解：进入溯源时主动播报一句引导。 */
function enqueueUpstreamIntroVoice() {
  if (!voice.enabled.value) return
  voice.enqueue({
    id: 'step:5:upstream:intro',
    stepIndex: STEP_INDICES.RULE,
    phase: 'upstream',
    kind: 'guide',
    text: VOICE_GUIDE.upstreamIntro,
    priority: 0,
  })
}

function ensureEvidenceIntroVoice() {
  if (!voice.enabled.value || voiceSentForStep.has(STEP_INDICES.PROBLEM_EVIDENCE)) return
  voiceSentForStep.add(STEP_INDICES.PROBLEM_EVIDENCE)
  voice.enqueue(buildEvidenceIntroCue())
}

function flushPendingRuleEngineVoice() {
  if (!voice.enabled.value || !pendingRuleEngineVoice) return
  const cue = buildRuleCue(pendingRuleEngineVoice)
  pendingRuleEngineVoice = null
  if (cue) voice.enqueue(cue)
}

function ensureDataFetchGuideVoice() {
  if (!voice.enabled.value || dataFetchGuideQueued) return
  dataFetchGuideQueued = true
  voiceSentForStep.add(STEP_INDICES.DATA_FETCH)
  voice.enqueue({
    id: 'step:3:data-fetch:guide',
    stepIndex: STEP_INDICES.DATA_FETCH,
    phase: 'dataFetch',
    kind: 'guide',
    text: VOICE_GUIDE.dataFetch,
    priority: 0,
  })
}

/** 治理建议步骤旁白：在 conclusion 呈现时主动调度，避免拖到技能固化步骤才播放。 */
function ensureSuggestionGuideVoice() {
  if (!voice.enabled.value || voiceSentForStep.has(STEP_INDICES.SUGGESTION)) return
  void scheduleProcessStepVoice(STEP_INDICES.SUGGESTION)
}

function rememberIntersectionName(name: string) {
  const trimmed = name.trim()
  if (!trimmed) return
  lastIntersectionName.value = trimmed
  void scheduleProcessStepVoice(STEP_INDICES.INTERSECTION)
}

async function waitForStepVoiceSent(stepIndex: number, timeoutMs = 15000) {
  if (!voice.enabled.value) return
  const deadline = Date.now() + timeoutMs
  while (!voiceSentForStep.has(stepIndex)) {
    if (Date.now() >= deadline) return
    await sleep(50)
  }
}

async function waitForPriorStepVoices(stepIndex: number) {
  for (let i = 0; i < stepIndex; i++) {
    if (i === STEP_INDICES.DATA_FETCH) continue
    await waitForStepVoiceSent(i)
    await voice.whenIdle()
  }
}

function handleProcessStepVoice(stepIndex: number) {
  if (!voice.enabled.value || voiceSentForStep.has(stepIndex)) return
  if (stepIndex === STEP_INDICES.DATA_FETCH) return
  const text = resolveProcessStepVoice(stepIndex, {
    intersectionName: lastIntersectionName.value,
  })
  if (!text) return
  voiceSentForStep.add(stepIndex)
  voice.enqueue({
    id: `step:${stepIndex}:guide`,
    stepIndex,
    phase: processStepPhase(stepIndex),
    kind: 'guide',
    text,
    priority: 0,
  })
}

async function scheduleProcessStepVoice(stepIndex: number) {
  if (!voice.enabled.value || voiceSentForStep.has(stepIndex)) return
  if (stepIndex === STEP_INDICES.DATA_FETCH) return

  await waitForPriorStepVoices(stepIndex)

  if (stepIndex === STEP_INDICES.INTERSECTION) {
    const gap = voiceConfig.playback.intersectionGuideGapMs ?? 900
    if (gap > 0) await sleep(gap)
    if (voiceSentForStep.has(stepIndex)) return
  }
  handleProcessStepVoice(stepIndex)
}

const {
  steps: processSteps,
  enqueue: enqueueProcess,
  reset: resetProcess,
  toggleStep,
  toggleDetails,
  whenIdle: whenProcessIdle,
} = useUnderstandingProcess({
  onStepStart(stepIndex) {
    void scheduleProcessStepVoice(stepIndex)
    if (stepIndex === STEP_INDICES.DATA_FETCH) {
      scheduleRevealRuntimePanel()
    }
    if (stepIndex === STEP_INDICES.RULE) {
      flushPendingRuleEngineVoice()
    }
  },
  onStepComplete(stepIndex) {
    presentation.revealInsightsForProcessStep(stepIndex)
    if (stepIndex === STEP_INDICES.COGNITION) {
      flushDeferredPresentationStep()
      scheduleRevealRuntimePanel()
    }
  },
})

const {
  state: skillBuildState,
  applyEvent: applySkillBuildEventRaw,
  beginExit: beginSkillBuildExit,
  close: closeSkillBuild,
  selectFile: selectSkillFile,
  reset: resetSkillBuild,
} = useSkillBuildProcess()

const skillBuildPendingFinish = ref(false)

const panelLayout = ref<'single' | 'stacked'>('single')

const {
  state: absorptionState,
  applyEvent: applyAbsorptionEvent,
  reset: resetAbsorption,
} = useExperienceAbsorption()

// 经验验证浮层 Toast（右下角向上弹出）：替代经验吸收卡片
const absorptionToasts = useAbsorptionToasts()

const { whenSettled: whenPresentationSettled, whenProcessAndVoiceSettled, whenVoiceIdle } =
  createPresentationBarrier({
    whenProcessIdle,
    voice,
    getAbsorptionState: () => absorptionState,
  })

/** 仅第一步「理解描述」语音播完后再进入锁定路口，避免「分析」被截断。 */
async function awaitUnderstandVoiceGate() {
  if (!voice.enabled.value) return
  await waitForStepVoiceSent(STEP_INDICES.UNDERSTAND)
  await voice.whenIdle()
}

/** 渠化全屏或技能固化/经验吸收演示时隐藏输入框，避免遮挡左侧终端 */
const hideInputDock = computed(
  () =>
    skillBuildState.visible ||
    absorptionState.active ||
    (channelizationActive.value &&
      inputLocked.value &&
      !analysisTerminalMode.value &&
      !showConfirm.value &&
      !followUpBubble.value &&
      !awaitingSuggestionConfirm.value),
)

let abortController: AbortController | null = null
let toastTimer: number | null = null
let suggestionConfirmQueued = false

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function syncEvidenceMapOverlay() {
  const stage = workbenchRef.value?.mapStageRef ?? mapStageRef.value
  stage?.setEvidenceOverlay(presentation.state.evidence, presentation.state.constraints)
}

watch(
  () => [presentation.state.evidence, presentation.state.constraints, presentation.state.cognition],
  () => syncEvidenceMapOverlay(),
  { deep: true },
)

function patchSuggestionPayload(raw: Record<string, unknown> | null | undefined) {
  if (!raw) return
  const payload: GovernanceSuggestionPayload = {
    narrative: typeof raw.narrative === 'string' ? raw.narrative : undefined,
    delta_seconds:
      typeof raw.delta_seconds === 'number' ? raw.delta_seconds : undefined,
    direction: typeof raw.direction === 'string' ? raw.direction : undefined,
    rule_id: typeof raw.rule_id === 'string' ? raw.rule_id : undefined,
    references: Array.isArray(raw.references)
      ? (raw.references as GovernanceSuggestionPayload['references'])
      : undefined,
  }
  if (payload.narrative || payload.delta_seconds != null) {
    presentation.patchGovernanceSuggestion(payload)
  }
}

function applyMetaEvidence(meta: MessageResponse['meta'], options?: { setConclusionPhase?: boolean }) {
  if (meta?.problem_evidence) {
    presentation.patchEvidence(meta.problem_evidence as ProblemEvidence)
  }
  if (meta?.flow_timing_governance) {
    presentation.patchFlowTimingGovernance(
      meta.flow_timing_governance as import('./types/evidence').FlowTimingGovernance,
    )
  }
  if (meta?.quantitative_constraints) {
    presentation.patchConstraints(meta.quantitative_constraints as QuantitativeConstraints)
    if (options?.setConclusionPhase) {
      presentation.setPhase('conclusion')
    }
  }
  if (Array.isArray(meta?.reused_experience)) {
    presentation.setReusedExperience(meta.reused_experience as string[])
  }
  if (Array.isArray(meta?.case_experience)) {
    presentation.setCaseExperience(
      meta.case_experience as import('./types/experience').CaseScenario[],
    )
  }
}

function formatEvidenceStepText(data: Record<string, unknown>): string {
  const items = buildEvidenceListItems(data as ProblemEvidence)
  return items.map((item) => `· ${item}`).join('\n')
}

function skillStageLabel(stage: string): string | null {
  return SKILL_BUILD_STAGES.find((s) => s.key === stage)?.label ?? null
}

function applySkillAbsorptionEvent(event: import('./types/skillAbsorption').SkillAbsorptionEvent) {
  applyAbsorptionEvent(event)
  if (event.type === 'skill_absorption_start') {
    panelLayout.value = 'stacked'
    enqueueProcess(STEP_INDICES.SKILL, '经验吸收追踪已启动…', true, true)
    voice.enqueue({
      id: 'step:7:absorption:start',
      stepIndex: STEP_INDICES.SKILL,
      phase: 'absorption',
      kind: 'transition',
      text: VOICE_GUIDE.absorptionStart,
      priority: 0,
    })
  }
  if (event.type === 'stage_start') {
    const line = ABSORPTION_STAGE_VOICE[event.stage]
    if (line) {
      voice.enqueue({
        id: `step:7:absorption:${event.stage}`,
        stepIndex: STEP_INDICES.SKILL,
        phase: event.stage,
        kind: 'guide',
        text: line,
        priority: 0,
      })
    }
  }
  if (event.type === 'skill_absorption_done') {
    enqueueProcess(STEP_INDICES.SKILL, '经验吸收与技能写入完成。', true, true)
    voice.enqueue({
      id: 'step:7:absorption:done',
      stepIndex: STEP_INDICES.SKILL,
      phase: 'absorption',
      kind: 'transition',
      text: VOICE_GUIDE.absorptionDone,
      priority: 0,
    })
  }
}

function applySkillBuildEvent(event: import('./types/skillBuild').SkillBuildEvent) {
  applySkillBuildEventRaw(event)
  if (panelMode.value !== 'analysis') return

  const payload = event.payload
  switch (event.type) {
    case 'drawer_open':
      break
    case 'skill_build_start':
      if (payload.interleaved) {
        voice.enqueue({
          id: 'step:7:skill_build:start',
          stepIndex: STEP_INDICES.SKILL,
          phase: 'skill_build',
          kind: 'transition',
          text: VOICE_GUIDE.skillBuildStart,
          priority: 0,
        })
      }
      break
    case 'stage_start': {
      if (skillBuildState.interleaved && ['understanding', 'planning'].includes(event.stage)) {
        break
      }
      const label = skillStageLabel(event.stage)
      if (label) enqueueProcess(STEP_INDICES.SKILL, `· ${label}`, true, true)
      break
    }
    case 'file_created':
      if (payload.path) enqueueProcess(STEP_INDICES.SKILL, `· 写入 ${payload.path}`, true, true)
      break
    case 'skill_build_done':
      leaderboardRefreshKey.value += 1
      enqueueProcess(
        STEP_INDICES.SKILL,
        `技能包已生成${payload.download_url ? '，可下载' : ''}。`,
        true,
        true,
      )
      voice.enqueue({
        id: 'step:7:skill_build:done',
        stepIndex: STEP_INDICES.SKILL,
        phase: 'skill_build',
        kind: 'transition',
        text: VOICE_GUIDE.skillBuildDone,
        priority: 0,
      })
      break
    default:
      break
  }
}

const skillEventBuffer: SkillBufferedEvent[] = []
let skillBufferFlushing = false

function resetSkillEventBuffer() {
  skillEventBuffer.length = 0
  skillBufferFlushing = false
}

function enqueueSkillPauseGate(settle: () => Promise<void>) {
  analysisQueue.enqueue(async () => {
    await settle()
  }, STEP_PAUSE_MS)
}

function applySkillBufferedEvent(item: SkillBufferedEvent) {
  if (item.domain === 'absorption') {
    applySkillAbsorptionEvent(item.event)
    if (shouldEnqueueAbsorptionPauseGate(item.event.type)) {
      enqueueSkillPauseGate(() => whenPresentationSettled())
    }
    return
  }
  applySkillBuildEvent(item.event)
  if (shouldEnqueueSkillBuildPauseGate(item.event.type)) {
    enqueueSkillPauseGate(() => whenProcessAndVoiceSettled())
  }
}

async function flushSkillEventBuffer() {
  if (skillBufferFlushing || skillEventBuffer.length === 0) return
  skillBufferFlushing = true
  try {
    while (skillEventBuffer.length > 0) {
      const item = skillEventBuffer.shift()!
      applySkillBufferedEvent(item)
      if (isSkillStreamBufferedEvent(item)) {
        await frameYield()
      }
    }
  } finally {
    skillBufferFlushing = false
  }
}

function dispatchSkillAbsorptionEvent(event: import('./types/skillAbsorption').SkillAbsorptionEvent) {
  if (presentationPause.paused.value) {
    skillEventBuffer.push({ domain: 'absorption', event })
    return
  }
  applySkillBufferedEvent({ domain: 'absorption', event })
}

function dispatchSkillBuildEvent(event: import('./types/skillBuild').SkillBuildEvent) {
  if (presentationPause.paused.value) {
    skillEventBuffer.push({ domain: 'build', event })
    return
  }
  applySkillBufferedEvent({ domain: 'build', event })
}

watch(
  () => presentationPause.paused.value,
  (paused, wasPaused) => {
    if (wasPaused && !paused) void flushSkillEventBuffer()
  },
)

function isPresentationPauseActive(): boolean {
  if (awaitingSuggestionConfirm.value) return false
  return (
    loading.value ||
    analysisQueue.isRunning ||
    presentationPause.paused.value ||
    isSkillPresentationActive(
      absorptionState.active,
      skillBuildState.visible,
      skillBuildState.status,
    )
  )
}

function pushMapAction(action: MapActionEvent) {
  mapActions.value.push(action)
}

function clearToastTimer() {
  if (toastTimer) {
    window.clearTimeout(toastTimer)
    toastTimer = null
  }
}

function isSuggestionGenerateConfirm(result: MessageResponse): boolean {
  return (
    result.state === 'awaiting_confirm' &&
    result.meta?.suggestion_action === 'awaiting_generate'
  )
}

function startSuggestionConfirmPause(message: string) {
  awaitingSuggestionConfirm.value = true
  pendingConfirm.value = true
  showConfirm.value = false
  confirmMessage.value = message
  docked.value = true
  inputLocked.value = false
  presentationPause.pause()
}

function queueSuggestionConfirmPause(message: string) {
  if (suggestionConfirmQueued || awaitingSuggestionConfirm.value) return
  suggestionConfirmQueued = true
  docked.value = true
  analysisQueue.enqueue(async () => {
    suggestionConfirmQueued = false
    await revealSuggestionStep(message, { silent: true })
    startSuggestionConfirmPause(message)
  }, STEP_PAUSE_MS)
}

function enterAnalysisTerminal() {
  analysisTerminalMode.value = true
  inputLocked.value = true
  pendingConfirm.value = false
  showConfirm.value = false
  docked.value = true
}

async function enterAnalysisTerminalAfterSuggestionPresented(
  skillAction: string | undefined,
  state: string,
) {
  if (!shouldEnterAnalysisTerminal(skillAction, state)) return
  await waitForGovernanceSuggestionPresented({
    whenQueueIdle: () => analysisQueue.whenIdle(),
    whenSettled: whenPresentationSettled,
    getFocusStepIndex: () => presentationSequence.focusStepIndex.value,
    getSuggestion: () => presentation.state.governanceSuggestion,
    getFlowTimingGovernance: () => presentation.state.flowTimingGovernance,
  })
  if (!shouldEnterAnalysisTerminal(skillAction, state)) return
  enterAnalysisTerminal()
}

function stopSuggestionConfirmPause({ resumeQueue = true } = {}) {
  suggestionConfirmQueued = false
  awaitingSuggestionConfirm.value = false
  pendingConfirm.value = false
  pendingSkillCreateConfirm.value = false
  clearToastTimer()
  mapToast.value = null
  if (resumeQueue) presentationPause.resume()
}

function syncPresentationFromAction(action?: Pick<MapActionEvent, 'phase' | 'focus_step_index'>) {
  if (action?.focus_step_index != null) {
    const target = action.focus_step_index
    if (target > STEP_INDICES.COGNITION && !isCognitionStepDone()) {
      pendingPresentationStepIndex = Math.max(pendingPresentationStepIndex ?? target, target)
    } else {
      presentationSequence.syncFromStepIndex(target)
    }
  }
  if (action?.phase) {
    presentationSequence.syncFromPhase(action.phase as PipelinePhase)
  }
}

function enqueueWithPresentation(
  index: number,
  text: string,
  append = false,
  silent = false,
  action?: Pick<MapActionEvent, 'step_summary' | 'focus_step_index' | 'phase'>,
) {
  if (index > STEP_INDICES.COGNITION && !isCognitionStepDone()) {
    pendingPresentationStepIndex = Math.max(pendingPresentationStepIndex ?? index, index)
    syncPresentationFromAction({ phase: action?.phase })
  } else {
    presentationSequence.syncFromStepIndex(index)
    syncPresentationFromAction(action)
  }
  const summary = action?.step_summary?.trim()
  if (summary) {
    enqueueProcess(index, text, append, silent, { summary, detail: text })
  } else {
    enqueueProcess(index, text, append, silent)
  }
}

function formatUnderstandingText(
  fields: Array<{ key: string; label: string; value: string }>,
): string {
  return fields.map((f) => `${f.label}：${f.value}`).join('\n')
}

function formatLinksText(links: IntersectionLink[]): string {
  if (!links.length) return '正在从路网库检索该路口关联 link…'
  const lines = links.slice(0, 10).map((l) => {
    const role =
      l.link_role === 'entrance' || l.link_role === '进口'
        ? '进口'
        : l.link_role === 'exit' || l.link_role === '出口'
          ? '出口'
          : l.link_role
    const name = l.road_name || l.link_id.slice(0, 14)
    return `· ${l.dir4_label || '—'}${role} ${name}（${l.lane_num ?? '—'} 车道）`
  })
  return [`共 ${links.length} 条关联 link，已在地图高亮：`, ...lines].join('\n')
}

function hasSkillStep() {
  return processSteps.value.some((s) => s.index === STEP_INDICES.SKILL)
}

function pushSkillStep(message: string) {
  if (panelMode.value !== 'analysis') return
  if (!hasSkillStep()) {
    enqueueProcess(STEP_INDICES.SKILL, message)
  } else {
    enqueueProcess(STEP_INDICES.SKILL, message, true)
  }
}

async function revealSkillStep(message: string) {
  await whenPresentationSettled()
  pushSkillStep(message)
  await whenPresentationSettled()
}

async function revealSuggestionStep(message: string, { silent = false } = {}) {
  await whenPresentationSettled()
  enqueueProcess(STEP_INDICES.SUGGESTION, message, true, silent)
  await whenPresentationSettled()
}

function governanceSuggestionPresentationGate() {
  return {
    whenQueueIdle: () => analysisQueue.whenIdle(),
    whenSettled: whenPresentationSettled,
    getFocusStepIndex: () => presentationSequence.focusStepIndex.value,
    getSuggestion: () => presentation.state.governanceSuggestion,
    getFlowTimingGovernance: () => presentation.state.flowTimingGovernance,
  }
}

function extractSkillSolidificationPrompt(content: string): string | null {
  const match = content.match(/---\n([\s\S]+?)回复「是」/)
  return match?.[1]?.trim() ?? null
}

/** 治理建议卡片揭示后再展示技能固化步骤与确认弹窗。 */
async function presentSkillSolidificationConfirm(
  message: string,
  { insideAnalysisQueue = false } = {},
) {
  if (showConfirm.value || skillSolidificationPresenting) return
  skillSolidificationPresenting = true
  try {
    confirmMessage.value = message
    pendingConfirm.value = true
    pendingSkillCreateConfirm.value = true
    if (!insideAnalysisQueue) {
      await analysisQueue.whenIdle()
    }
    await waitForGovernanceSuggestionPresented({
      ...governanceSuggestionPresentationGate(),
      skipQueueIdle: true,
    })
    if (
      !pendingConfirm.value ||
      awaitingSuggestionConfirm.value ||
      suggestionConfirmQueued ||
      showConfirm.value
    ) {
      return
    }
    if (!hasSkillStep()) {
      await revealSkillStep(message)
    }
    if (voice.enabled.value) {
      await waitForStepVoiceSent(STEP_INDICES.SUGGESTION, 3000)
      await voice.whenIdle()
    }
    showConfirm.value = true
    inputLocked.value = false
  } finally {
    skillSolidificationPresenting = false
  }
}

async function finalizeDiagnosisUi(result: MessageResponse) {
  if (panelMode.value !== 'analysis') return

  if (isSuggestionGenerateConfirm(result)) {
    queueSuggestionConfirmPause(result.reply.content || confirmMessage.value)
    return
  }

  await analysisQueue.whenIdle()
  await whenPresentationSettled()

  const skillAction = result.meta?.skill_action as string | undefined
  const entersTerminal = shouldEnterAnalysisTerminal(skillAction, result.state)

  if (
    entersTerminal &&
    hasSuggestionCardContent(
      presentation.state.governanceSuggestion,
      presentation.state.flowTimingGovernance,
    ) &&
    presentationSequence.focusStepIndex.value < STEP_INDICES.SUGGESTION
  ) {
    const text =
      buildSuggestionPlainText(
        presentation.state.governanceSuggestion,
        presentation.state.flowTimingGovernance,
      ) ?? '运行指标平稳，已记录并将持续关注。'
    await revealSuggestionStep(text, { silent: true })
    await whenPresentationSettled()
  }

  if (entersTerminal) {
    await enterAnalysisTerminalAfterSuggestionPresented(skillAction, result.state)
    return
  }

  if (result.state === 'awaiting_confirm' && skillAction === 'awaiting_create') {
    if (!showConfirm.value && pendingConfirm.value) {
      const prompt =
        confirmMessage.value ||
        extractSkillSolidificationPrompt(result.reply.content) ||
        '已生成治理建议，是否将本次诊断和约束沉淀为路口 Skill？'
      await presentSkillSolidificationConfirm(prompt)
    }
    return
  }

  if (!hasSkillStep()) {
    if (shouldShowSkillSolidificationStep(skillAction, result.state)) {
      await revealSkillStep(
        confirmMessage.value ||
          '是否将此诊断固化为路口 Skill？回复「是」确认固化，「否」结束本次会话。',
      )
    }
  }

  if (pendingConfirm.value) {
    showConfirm.value = true
    if (!entersTerminal) inputLocked.value = false
  } else if (result.state !== 'awaiting_confirm' && !entersTerminal && !analysisTerminalMode.value) {
    inputLocked.value = false
  }
}

async function tryShowConfirm() {
  if (
    analysisTerminalMode.value ||
    !pendingConfirm.value ||
    showConfirm.value ||
    awaitingSuggestionConfirm.value ||
    suggestionConfirmQueued
  ) {
    return
  }
  if (pendingSkillCreateConfirm.value) {
    const prompt =
      confirmMessage.value ||
      '已生成治理建议，是否将本次诊断和约束沉淀为路口 Skill？'
    await presentSkillSolidificationConfirm(prompt)
    return
  }
  await analysisQueue.whenIdle()
  await whenPresentationSettled()
  if (!pendingConfirm.value || awaitingSuggestionConfirm.value || suggestionConfirmQueued) return
  showConfirm.value = true
  inputLocked.value = false
}

function upsertStep(event: {
  step?: string
  label?: string
  status?: string
  data?: Record<string, unknown>
  timestamp?: string
}) {
  if (!event.step) return
  if (event.step.startsWith('experience_') && event.status === 'completed') {
    const level = event.step.replace('experience_', '') as
      | 'cognition'
      | 'diagnosis'
      | 'solution'
    const d = event.data ?? {}
    const text =
      (d.text as string) ||
      (d.cause as string) ||
      (d.measure as string) ||
      (d.quantified as string) ||
      (d.skill_id as string) ||
      ''
    // 认知画像：数据支撑则已验证(verified)，否则待验证(pending)
    const status =
      level === 'cognition'
        ? d.status === 'verified'
          ? 'verified'
          : 'pending'
        : undefined
    const tagsFromServer = Array.isArray(d.tags) ? (d.tags as string[]) : undefined
    const tags: string[] =
      tagsFromServer ??
      (level === 'cognition'
        ? ['认知画像', '问题记录', d.status === 'verified' ? '已验证' : '待验证']
        : level === 'diagnosis'
          ? ['诊断经验', '用户口述', String(d.dimension || '用户观察')]
          : ['方案经验', '治理措施'])
    if (text) presentation.addExperienceSediment({ level, text, status, tags })

    // 认知/诊断经验：右下角浮层 Toast 显式反馈吸收/去重结果
    if (text && (level === 'cognition' || level === 'diagnosis')) {
      const action = ['inserted', 'exists', 'updated'].includes(String(d.action))
        ? (d.action as 'inserted' | 'exists' | 'updated')
        : 'inserted'
      absorptionToasts.push(
        level === 'cognition'
          ? {
              kind: 'cognition',
              status: d.status === 'verified' ? 'verified' : 'data_doubt',
              action,
              tags,
              text,
            }
          : { kind: 'diagnosis', action, tags, text },
      )
    }
  }
  const idx = steps.value.findIndex((s) => s.step === event.step && s.status === 'running')
  const record: StepRecord = {
    step: event.step,
    label: event.label ?? event.step,
    status: event.status ?? 'running',
    data: event.data,
    timestamp: event.timestamp,
  }
  if (event.status === 'running') {
    steps.value.push(record)
  } else if (idx >= 0) {
    steps.value[idx] = { ...steps.value[idx], ...record }
  } else {
    steps.value.push(record)
  }
}

function isFollowUpResult(result: MessageResponse): boolean {
  if (isSuggestionGenerateConfirm(result)) return false
  return (
    result.reply.type === 'follow_up' ||
    result.reply.type === 'corridor_scan' ||
    result.state === 'nlu_incomplete' ||
    result.state === 'corridor_nlu_incomplete' ||
    result.state === 'awaiting_corridor_pick' ||
    result.state === 'intersection_ambiguous'
  )
}

function formatConversationSummary(): string {
  return conversationTurns.value
    .map((t) => (t.role === 'user' ? `用户：${t.content}` : `助手：${t.content}`))
    .join('\n')
}

function syncCorridorScanFromScene(action: MapActionEvent) {
  const intersections = (action.intersections ?? []) as unknown as CorridorIntersectionItem[]
  if (!intersections.length) return
  presentation.setCorridorScan({
    lineName: action.corridor?.line_name || '干线',
    timePeriodLabel: action.time_period?.label || '时段',
    intersections,
    focusInterId: action.focus_inter_id ?? null,
  })
}

function syncCorridorScanFromMeta(meta: MessageResponse['meta']) {
  const scan = meta?.corridor_scan as
    | {
        road_name?: string
        line_name?: string
        time_period?: { label?: string }
        intersections?: CorridorIntersectionItem[]
      }
    | undefined
  if (!scan?.intersections?.length) {
    const scene = meta?.corridor_scan_scene as MapActionEvent | undefined
    if (scene) syncCorridorScanFromScene(scene)
    return
  }
  const scene = meta?.corridor_scan_scene as MapActionEvent | undefined
  presentation.setCorridorScan({
    lineName: scan.road_name || scan.line_name || '干线',
    timePeriodLabel: scan.time_period?.label || '时段',
    intersections: scan.intersections,
    focusInterId: scene?.focus_inter_id ?? null,
  })
  if (scene?.hud) {
    presentation.setHud(scene.hud)
  }
}

function handleCorridorSelect(interId: string) {
  presentation.selectCorridorIntersection(interId)
  const item = presentation.state.corridorScan?.intersections.find((i) => i.inter_id === interId)
  if (item?.lon != null && item?.lat != null) {
    void workbenchRef.value?.mapStageRef?.focusCorridorIntersection(item.lon, item.lat)
  }
  if (sessionState.value === 'awaiting_corridor_pick' && item?.inter_name && !loading.value) {
    void handleSend(item.inter_name)
  }
}

function enterConversationMode(result: MessageResponse) {
  panelMode.value = 'conversation'
  sessionState.value = result.state
  docked.value = true
  followUpBubble.value = null
  missingFields.value = (result.meta?.missing_fields as string[]) ?? []
  resetProcess()
  analysisQueue.reset()
  pendingNarration = null

  const last = conversationTurns.value[conversationTurns.value.length - 1]
  const tag = result.reply.type === 'corridor_scan' ? '干线扫描' : '追问'
  if (!last || last.role !== 'assistant' || last.content !== result.reply.content) {
    conversationTurns.value.push({
      role: 'assistant',
      content: result.reply.content,
      tag,
    })
  }
  if (result.reply.type === 'corridor_scan') {
    presentation.setPhase('corridor_scan')
    syncCorridorScanFromMeta(result.meta)
    if (result.meta?.corridor_scan_scene) {
      pushMapAction(result.meta.corridor_scan_scene as MapActionEvent)
    }
  }
  inputLocked.value = false
}

function beginAnalysisFlow(userContent: string) {
  panelMode.value = 'analysis'
  followUpBubble.value = null
  missingFields.value = []
  docked.value = true
  prepareNewAnalysisRun(userContent)
  const intro =
    conversationTurns.value.length > 0
      ? formatConversationSummary()
      : `用户描述：${userContent}`
  conversationTurns.value = []
  presentationSequence.syncFromStepIndex(STEP_INDICES.UNDERSTAND)
  enqueueProcess(STEP_INDICES.UNDERSTAND, intro)
}

function prepareNewAnalysisRun(userContent: string) {
  stopSuggestionConfirmPause()
  analysisTerminalMode.value = false
  presentationPause.reset()
  analysisQueue.reset()
  resetSkillEventBuffer()
  resetProcess()
  steps.value = []
  presentation.prepareNewAnalysisRun()
  mapActions.value = []
  pendingNarration = null
  analysisRunKey.value += 1
  lastIntersectionName.value = null
  voiceSentForStep.clear()
  dataFetchGuideQueued = false
  pendingPresentationStepIndex = null
  pendingRuleEngineVoice = null
  clearRuntimeRevealTimer()
  presentationSequence.reset()
  voice.resetSession()
  void workbenchRef.value?.mapStageRef?.prepareNewAnalysisRun()
  lastUserContent = userContent
}

function handleNluStep(data: Record<string, unknown>) {
  if (data.status === 'incomplete') {
    missingFields.value = (data.missing as string[]) ?? []
  }
}

function applySceneHighlight(action: MapActionEvent) {
  if (action.focus_groups?.length) {
    presentation.setFocusedDirs(action.focus_groups)
  } else if (action.highlight_dirs?.length) {
    presentation.setHighlightDirs(action.highlight_dirs)
  }
  if (action.protected_groups?.length) {
    presentation.setProtectedGroups(action.protected_groups)
  }
  if (action.highlight_turn) {
    presentation.setHighlightTurn(
      parseHighlightTurn(action.highlight_turn),
    )
  } else if (action.phase && action.phase !== 'granularity') {
    presentation.setHighlightTurn(null)
  }
  if (action.phase) {
    const phase = action.phase as PipelinePhase
    presentation.setPhase(phase)
    presentationSequence.syncFromPhase(phase)
  }
  if (action.hud) {
    presentation.setHud(action.hud)
  }
}

function enqueueLinksVoice(action: MapActionEvent) {
  if (!voice.enabled.value) return
  if (voiceSentForStep.has(STEP_INDICES.COGNITION)) return
  const cue = buildCognitionVoiceCue({
    speakable: action.speakable,
    axis_roads: action.axis_roads,
    intersectionName: lastIntersectionName.value,
  })
  if (!cue) return
  voiceSentForStep.add(STEP_INDICES.COGNITION)
  voice.enqueue(cue)
}

// 配时（timing）不再随数据铺陈口播「周期 N 秒」；其相关读法将按问题类型按需触发
const NARRATION_TEXT_VOICE_PHASES = new Set(['traffic'])

function enqueueNarrationPhaseVoice(action: MapActionEvent) {
  if (!voice.enabled.value) return
  if (presentationSequence.focusStepIndex.value < STEP_INDICES.DATA_FETCH) return
  const phase = action.phase ?? ''
  if (!NARRATION_TEXT_VOICE_PHASES.has(phase)) return
  ensureDataFetchGuideVoice()
  const cue = buildNarrationPhaseVoiceCue(phase, action.text ?? '', action.title)
  if (cue) voice.enqueue(cue)
}

function enqueueSceneVoice(action: MapActionEvent) {
  if (!voice.enabled.value) return
  if (presentationSequence.focusStepIndex.value < STEP_INDICES.DATA_FETCH) return
  ensureDataFetchGuideVoice()
  if (action.phase === 'direction' && action.direction_roles?.length) {
    const cue = buildDirectionVoiceCue(action.direction_roles as DirectionRoleRow[])
    if (cue) voice.enqueue(cue)
    return
  }
  if (action.phase === 'imbalance') {
    const imb = presentation.state.runtimeMetrics?.imbalance_index
    const cue = buildImbalanceCue(imb)
    if (cue) voice.enqueue(cue)
  }
}

function handleNarration(action: MapActionEvent) {
  const text = action.text ?? ''
  if (!text && !action.step_summary) return

  const narrOpts = action

  if (action.phase === 'links' || action.phase === 'channelization') {
    if (action.phase === 'links') {
      enqueueLinksVoice(action)
    }
    enqueueWithPresentation(STEP_INDICES.COGNITION, text, false, false, narrOpts)
    return
  }
  if (
    action.phase === 'traffic' ||
    action.phase === 'direction' ||
    action.phase === 'timing' ||
    action.phase === 'imbalance'
  ) {
    ensureDataFetchGuideVoice()
    const prefix = action.title ? `${action.title}：` : ''
    const silentBeat = isDataFetchSubBeat(action.phase)
    enqueueWithPresentation(
      STEP_INDICES.DATA_FETCH,
      `${prefix}${text}`,
      true,
      silentBeat,
      narrOpts,
    )
    enqueueNarrationPhaseVoice(action)
    return
  }
  if (action.phase === 'rule') {
    presentation.setPhase('rule')
    presentationSequence.syncFromPhase('rule')
    presentationSequence.syncFromStepIndex(STEP_INDICES.RULE)
    enqueueWithPresentation(STEP_INDICES.RULE, text, false, false, narrOpts)
    void scheduleProcessStepVoice(STEP_INDICES.RULE)
    return
  }
  if (action.phase === 'conclusion') {
    presentation.setPhase('conclusion')
    presentationSequence.syncFromPhase('conclusion')
    presentationSequence.syncFromStepIndex(STEP_INDICES.SUGGESTION)
    patchSuggestionPayload(action.suggestion)
    enqueueWithPresentation(STEP_INDICES.SUGGESTION, text, false, false, narrOpts)
    ensureSuggestionGuideVoice()
    return
  }
  if (action.phase === 'locate') {
    enqueueWithPresentation(STEP_INDICES.INTERSECTION, text, true, false, narrOpts)
  }
}

function updateCognitionFromAction(action: MapActionEvent) {
  if (!action.intersection) return
  const prev = presentation.state.cognition
  presentation.setCognition({
    intersection: action.intersection,
    arms: action.arms ?? prev?.arms ?? [],
    links: action.links ?? prev?.links ?? [],
    metrics_by_arm: action.metrics_by_arm ?? prev?.metrics_by_arm,
    metrics_by_turn: action.metrics_by_turn ?? prev?.metrics_by_turn,
    direction_groups: action.direction_groups ?? prev?.direction_groups,
    available_directions: prev?.available_directions,
  })
}

function handleMapStep(data: Record<string, unknown> | undefined, status: string) {
  if (!data?.action || status !== 'completed') return
  const action = data as unknown as MapActionEvent
  const isGenerateSuggestionConfirm =
    action.action === 'confirm_bubble' && action.action_type === 'generate_suggestion'

  if (isGenerateSuggestionConfirm) {
    if (suggestionConfirmQueued || awaitingSuggestionConfirm.value) return
    suggestionConfirmQueued = true
    docked.value = true
  }

  analysisQueue.enqueue(async () => {
    if (action.action === 'input_dock') {
      if (analysisTerminalMode.value) return
      if (action.phase === 'engage') {
        docked.value = true
        inputLocked.value = action.locked ?? true
      }
      if (action.phase === 'confirm') {
        inputLocked.value = !(action.locked === false)
      }
      return
    }

    if (action.action === 'show_understanding') {
      const fields = action.fields ?? []
      const userLine = lastUserContent ? `用户描述：${lastUserContent}` : ''
      const structured = formatUnderstandingText(fields)
      const block = userLine ? `${userLine}\n${structured}` : structured
      enqueueProcess(STEP_INDICES.UNDERSTAND, block, false, true)
      return
    }

    if (action.action === 'fly_to_intersection') {
      await awaitUnderstandVoiceGate()
      const inter = action.intersection
      if (inter?.name) {
        rememberIntersectionName(inter.name)
        enqueueProcess(
          STEP_INDICES.INTERSECTION,
          `已定位路口：${inter.name}`,
          true,
          true,
          {
            summary: formatLocatedIntersectionSummary(inter.name),
            detail: `已定位路口：${inter.name}`,
          },
        )
      }
      presentation.setPhase('locate')
      presentationSequence.syncFromPhase('locate')
      presentationSequence.syncFromStepIndex(STEP_INDICES.COGNITION)
      updateCognitionFromAction(action)
      pushMapAction(action)
      return
    }

    if (action.action === 'highlight_links') {
      updateCognitionFromAction(action)
      presentation.setHighlightTurn(null)
      presentation.setPhase('links')
      presentationSequence.syncFromPhase('links')
      presentationSequence.syncFromStepIndex(STEP_INDICES.COGNITION)
      const linksDetail = formatLinksText(action.links ?? [])
      const linkCount = action.links?.length ?? 0
      enqueueProcess(STEP_INDICES.COGNITION, linksDetail, false, true, {
        summary: linkCount
          ? `共 ${linkCount} 条关联路段，已在地图高亮。`
          : '正在检索路口关联路段。',
        detail: linksDetail,
      })
      pushMapAction(action)
      return
    }

    if (action.action === 'update_metrics') {
      updateCognitionFromAction(action)
      const ev = action.evaluation as Record<string, unknown> | undefined
      const tf = action.traffic_flow as Record<string, unknown> | undefined
      if (ev || tf) {
        const metrics: Array<{ label: string; value: string; severity?: string }> = []
        const armMetrics =
          (action.metrics_by_arm as Array<{ dir4_label?: string; saturation?: number }> | undefined) ??
          presentation.state.cognition?.metrics_by_arm ??
          []
        const approachOrder = ['东', '南', '西', '北'] as const
        for (const dir of approachOrder) {
          const arm = armMetrics.find((a) => {
            const label = String(a.dir4_label ?? '')
            return label.startsWith(dir)
          })
          if (arm?.saturation == null) continue
          const n = Number(arm.saturation)
          metrics.push({
            label: `${dir}进口饱和度`,
            value: n.toFixed(2),
            severity: n >= 0.8 ? 'high' : n >= 0.65 ? 'medium' : 'low',
          })
        }
        if (ev?.delay_index != null) {
          metrics.push({ label: '延误指数', value: Number(ev.delay_index).toFixed(2) })
        }
        if (ev?.imbalance_index != null) {
          metrics.push({ label: '失衡系数', value: Number(ev.imbalance_index).toFixed(2) })
        }
        if (ev?.level_of_service_label != null) {
          metrics.push({ label: '服务水平', value: String(ev.level_of_service_label) })
        }
        if (metrics.length) {
          presentation.mergeDataInsight({ title: '运行数据', icon: '📊', metrics })
        }
        presentation.patchRuntimeMetrics({
          saturation_rate:
            (tf?.saturation_rate as number | undefined) ??
            (ev?.saturation_rate as number | undefined) ??
            null,
          delay_index: (ev?.delay_index as number | undefined) ?? null,
          imbalance_index: (ev?.imbalance_index as number | undefined) ?? null,
          green_utilization: (ev?.green_utilization as number | undefined) ?? null,
        })
      }
      pushMapAction(action)
      return
    }

    if (action.action === 'narration') {
      if (PAIRED_NARRATION_PHASES.has(action.phase ?? '')) {
        pendingNarration = action
        return
      }
      handleNarration(action)
      return
    }

    if (action.action === 'map_scene') {
      const narration = pendingNarration
      pendingNarration = null
      if (narration) {
        handleNarration(narration)
      }
      applySceneHighlight(action)
      enqueueSceneVoice(action)
      if (isDataFetchSubBeat(action.phase)) {
        await whenVoiceIdle()
      } else {
        await whenPresentationSettled()
      }
      pushMapAction(action)
      return
    }

    if (action.action === 'corridor_scan_scene') {
      presentation.setPhase('corridor_scan')
      syncCorridorScanFromScene(action)
      if (action.hud) {
        presentation.setHud(action.hud)
      }
      pushMapAction(action)
      return
    }

    if (action.action === 'upstream_tree') {
      presentation.setPhase('rule')
      presentationSequence.syncFromPhase('rule')
      presentationSequence.syncFromStepIndex(STEP_INDICES.RULE)
      const targetTurn =
        (action.highlight_turn ? parseHighlightTurn(action.highlight_turn)?.label : null) ??
        presentation.state.highlightTurn?.label ??
        null
      const traceText = buildUpstreamProcessText(action.storyboard, targetTurn)
      if (traceText) {
        enqueueProcess(STEP_INDICES.RULE, traceText, true, true)
      }
      // RULE 步骤以 silent 方式入队（不触发 onStepStart），此处显式恢复
      // 原因诊断口播（步骤旁白 + 规则引擎结论）与流量溯源概要讲解。
      enqueueUpstreamIntroVoice()
      void scheduleProcessStepVoice(STEP_INDICES.RULE)
      flushPendingRuleEngineVoice()
      pushMapAction(action)
      const durationMs = upstreamStoryboardDurationMs(action.storyboard?.frames)
      if (durationMs > 0) {
        await sleep(durationMs)
      }
      await whenPresentationSettled()
      return
    }

    if (action.action === 'confirm_bubble') {
      if (action.action_type === 'generate_suggestion') {
        const message = action.message ?? '问题诊断成立，是否需要生成治理建议？'
        suggestionConfirmQueued = false
        await revealSuggestionStep(message, { silent: true })
        startSuggestionConfirmPause(message)
        return
      }
      await presentSkillSolidificationConfirm(
        action.message ??
          '已生成治理建议，是否将本次诊断和约束沉淀为路口 Skill？',
        { insideAnalysisQueue: true },
      )
      return
    }

    pushMapAction(action)
  }, resolveMapActionPauseMs(action))
}

function handleProblemEvidenceStep(data: Record<string, unknown>) {
  const text = formatEvidenceStepText(data)
  analysisQueue.enqueue(async () => {
    ensureEvidenceIntroVoice()
    const partial = data as unknown as ProblemEvidence & {
      quantitative_constraints?: QuantitativeConstraints
    }
    const chronic = partial.chronic
    let summary: string | undefined
    if (chronic?.is_chronic && chronic.window_days != null && chronic.congested_days != null) {
      summary = `近 ${chronic.window_days} 天中 ${chronic.congested_days} 天超标，问题成立。`
    } else if (partial.summary) {
      summary =
        partial.summary.length > 40 ? `${partial.summary.slice(0, 39)}…` : partial.summary
    }
    if (summary) {
      enqueueProcess(STEP_INDICES.PROBLEM_EVIDENCE, text, false, false, { summary, detail: text })
    } else {
      enqueueProcess(STEP_INDICES.PROBLEM_EVIDENCE, text)
    }
    presentationSequence.syncFromStepIndex(STEP_INDICES.PROBLEM_EVIDENCE)
    presentationSequence.syncFromPhase('evidence')
    presentation.patchEvidence({
      ...(presentation.state.evidence ?? {}),
      ...partial,
      summary: partial.summary ?? presentation.state.evidence?.summary,
      chronic: partial.chronic ?? presentation.state.evidence?.chronic,
      dow_pattern: partial.dow_pattern ?? presentation.state.evidence?.dow_pattern,
      metrics: partial.metrics ?? presentation.state.evidence?.metrics,
      by_direction: partial.by_direction ?? presentation.state.evidence?.by_direction,
      by_turn: partial.by_turn ?? presentation.state.evidence?.by_turn,
      by_approach: partial.by_approach ?? presentation.state.evidence?.by_approach,
      timing_profile: partial.timing_profile ?? presentation.state.evidence?.timing_profile,
      corridor_context: partial.corridor_context ?? presentation.state.evidence?.corridor_context,
      external_evidence: partial.external_evidence ?? presentation.state.evidence?.external_evidence,
      diagnosis_story: partial.diagnosis_story ?? presentation.state.evidence?.diagnosis_story,
    } as ProblemEvidence)
    presentation.setPhase('evidence')

    if (partial.quantitative_constraints) {
      presentation.patchConstraints(partial.quantitative_constraints)
    }

    const focused = presentation.state.evidence?.by_direction?.filter((d) => d.focused) ?? []
    if (focused.length) {
      presentation.setFocusedDirs(focused.map((d) => d.group))
    }
    await whenPresentationSettled()
  }, STEP_PAUSE_MS)
}

function handlePipelineStep(
  event: {
    step?: string
    status?: string
    data?: Record<string, unknown>
  },
  currentContent: string,
) {
  if (event.step === 'data_fetch' && event.status === 'running') {
    if (!processSteps.value.some((s) => s.index === STEP_INDICES.DATA_FETCH)) {
      analysisQueue.enqueue(async () => {
        ensureDataFetchGuideVoice()
        enqueueProcess(STEP_INDICES.DATA_FETCH, '正在拉取路口运行数据…', false, false, {
          summary: '正在获取运行数据',
        })
      }, 0)
    } else {
      ensureDataFetchGuideVoice()
    }
    return
  }

  if (event.status !== 'completed' || !event.step) return
  const data = event.data ?? {}

  if (event.step === 'nlu') {
    if (data.status === 'complete') {
      beginAnalysisFlow(currentContent)
    } else if (data.status === 'incomplete') {
      handleNluStep(data)
    }
    return
  }

  if (event.step === 'skill_match') {
    const notice = String(data.reuse_notice ?? '')
    if (notice) {
      analysisQueue.enqueue(async () => {
        const matched = Boolean(data.matched)
        const { summary, detail } = formatSkillReuseLines(notice, matched)
        enqueueProcess(STEP_INDICES.INTERSECTION, detail, true, true, { summary, detail })
        presentationSequence.syncFromStepIndex(STEP_INDICES.INTERSECTION)
        if (matched && voice.enabled.value) {
          const constraintMatch = notice.match(/历史约束[：:]\s*(.+?)(?:\n|$)/)
          const constraint = constraintMatch?.[1]?.trim()
          if (constraint) {
            voice.enqueue({
              id: 'step:1:skill-reuse',
              stepIndex: STEP_INDICES.INTERSECTION,
              phase: 'intersection',
              kind: 'guide',
              text: voiceTemplate('skillReuseHint', { constraint: `「${constraint}」` }),
              priority: 0,
            })
          }
        }
      }, STEP_PAUSE_MS)
    }
    return
  }

  if (event.step === 'intersection' && data.inter_name) {
    rememberIntersectionName(String(data.inter_name))
    analysisQueue.enqueue(async () => {
      await awaitUnderstandVoiceGate()
      const name = String(data.inter_name)
      enqueueProcess(STEP_INDICES.INTERSECTION, `路口匹配：${name}`, true, true, {
        summary: formatIntersectionMatchSummary(name),
        detail: `路口匹配：${name}`,
      })
      presentationSequence.syncFromStepIndex(STEP_INDICES.INTERSECTION)
    }, STEP_PAUSE_MS)
  }

  if (event.step === 'problem_evidence') {
    handleProblemEvidenceStep(data)
    return
  }

  if (event.step === 'data_fetch') {
    return
  }

  if (event.step === 'rule_engine') {
    if (data.flow_timing_governance) {
      presentation.patchFlowTimingGovernance(
        data.flow_timing_governance as import('./types/evidence').FlowTimingGovernance,
      )
      presentation.setPhase('rule')
      analysisQueue.enqueue(async () => {
        const gov = data.flow_timing_governance as {
          summary?: string
          primary_diagnosis?: { headline?: string }
        }
        enqueueProcess(
          STEP_INDICES.RULE,
          gov.primary_diagnosis?.headline ?? gov.summary ?? '四维信控诊断完成',
          true,
          true,
        )
        if (data.diagnosed) {
          pendingRuleEngineVoice = data
        }
        await whenPresentationSettled()
      }, STEP_PAUSE_MS)
    } else {
      if (data.diagnosed) {
        pendingRuleEngineVoice = data
      }
    }
    return
  }

  if (event.step === 'suggestion' && event.status === 'completed') {
    patchSuggestionPayload(data as Record<string, unknown>)
    return
  }
}

async function initSession() {
  abortController?.abort()
  stopSuggestionConfirmPause()
  presentationPause.reset()
  analysisQueue.reset()
  resetSkillEventBuffer()
  resetProcess()
  resetSkillBuild()
  resetAbsorption()
  panelLayout.value = 'single'
  presentation.reset()
  skillBuildPendingFinish.value = false
  loading.value = false
  inputLocked.value = false
  analysisTerminalMode.value = false
  docked.value = false
  showConfirm.value = false
  pendingConfirm.value = false
  pendingSkillCreateConfirm.value = false
  skillSolidificationPresenting = false
  awaitingSuggestionConfirm.value = false
  mapToast.value = null
  mapActions.value = []
  pendingNarration = null
  suggestionConfirmQueued = false
  lastIntersectionName.value = null
  voiceSentForStep.clear()
  dataFetchGuideQueued = false
  pendingPresentationStepIndex = null
  pendingRuleEngineVoice = null
  clearRuntimeRevealTimer()
  presentationSequence.reset()
  panelMode.value = 'idle'
  sessionState.value = 'idle'
  conversationTurns.value = []
  missingFields.value = []
  followUpBubble.value = null
  steps.value = []
  messages.value = []
  errorBanner.value = null
  await workbenchRef.value?.mapStageRef?.resetToCityDefault()
  try {
    const session = await createSession()
    sessionId.value = session.session_id
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorBanner.value = `创建会话失败: ${msg}`
  }
}

async function handleSend(content: string) {
  if (!sessionId.value || loading.value || inputLocked.value) return

  const isContinuation =
    sessionState.value === 'nlu_incomplete' ||
    sessionState.value === 'corridor_nlu_incomplete' ||
    sessionState.value === 'awaiting_corridor_pick'
  const wasSuggestionConfirm = awaitingSuggestionConfirm.value
  const isSkillConfirmReply = sessionState.value === 'awaiting_confirm'
  if (wasSuggestionConfirm) {
    inputLocked.value = true
    stopSuggestionConfirmPause()
  } else {
    clearToastTimer()
  }

  messages.value.push({ id: uid(), role: 'user', content })
  loading.value = true
  inputLocked.value = true
  errorBanner.value = null
  abortController = new AbortController()
  followUpBubble.value = null
  lastUserContent = content

  if (wasSuggestionConfirm) {
    panelMode.value = 'analysis'
    docked.value = true
    followUpBubble.value = null
    pendingNarration = null
  } else if (panelMode.value !== 'analysis' || isContinuation) {
    conversationTurns.value.push({ role: 'user', content })
  } else if (panelMode.value === 'analysis' && !isSkillConfirmReply) {
    prepareNewAnalysisRun(content)
    docked.value = true
    enqueueProcess(STEP_INDICES.UNDERSTAND, `用户描述：${content}`)
  } else {
    pendingNarration = null
    docked.value = false
  }

  if (!wasSuggestionConfirm) {
    showConfirm.value = false
    pendingConfirm.value = false
    pendingSkillCreateConfirm.value = false
  }

  try {
    await sendMessageStream(
      sessionId.value,
      content,
      {
        onStep: (event) => {
          upsertStep(event)
          if (event.step === 'map_action') {
            handleMapStep(event.data, event.status ?? 'completed')
          } else {
            handlePipelineStep(event, content)
          }
        },
        onSkillBuild: (event) => {
          dispatchSkillBuildEvent(event)
        },
        onSkillAbsorption: (event) => {
          dispatchSkillAbsorptionEvent(event)
        },
        onResult: (result) => {
          sessionState.value = result.state
          messages.value.push({
            id: uid(),
            role: 'assistant',
            content: result.reply.content,
            replyType: result.reply.type,
            meta: {
              state: result.state,
              nlu: result.nlu,
              diagnosis: result.diagnosis,
              suggestion: result.suggestion,
              ...result.meta,
            },
          })

          if (isFollowUpResult(result)) {
            enterConversationMode(result)
            return
          }

          if (result.reply.type === 'diagnosis' || result.state === 'awaiting_confirm') {
            panelMode.value = 'analysis'
            followUpBubble.value = null
          }

          if (result.state === 'awaiting_confirm') {
            pendingConfirm.value = true
            pendingSkillCreateConfirm.value = result.meta?.skill_action === 'awaiting_create'
            if (isSuggestionGenerateConfirm(result)) {
              docked.value = true
            }
          }

          if (result.meta?.active_dimensions || result.meta?.problem_types) {
            presentation.setActiveDimensions(
              (result.meta.active_dimensions as string[] | undefined) ?? [],
              (result.meta.problem_types as string[] | undefined) ?? [],
            )
          }

          if (result.meta?.cognition) {
            const cog = result.meta.cognition as unknown as CognitionPayload
            if (cog.intersection) {
              presentation.setCognition({
                intersection: cog.intersection,
                arms: cog.arms ?? presentation.state.cognition?.arms ?? [],
                links: presentation.state.cognition?.links,
                metrics_by_arm: presentation.state.cognition?.metrics_by_arm,
              })
            }
          }

          applyMetaEvidence(result.meta, {
            setConclusionPhase: Boolean(result.meta?.quantitative_constraints),
          })
          patchSuggestionPayload(result.suggestion as Record<string, unknown> | null | undefined)

          if (panelMode.value === 'analysis') {
            void finalizeDiagnosisUi(result)
          } else if (result.state !== 'awaiting_confirm') {
            inputLocked.value = false
          }

          const skillAction = result.meta?.skill_action as string | undefined
          if (skillAction === 'declined_create' || skillAction === 'declined_update') {
            panelLayout.value = 'single'
            resetAbsorption()
            void initSession()
          }
        },
        onError: (message, detail) => {
          errorBanner.value = detail ? `${message}: ${detail}` : message
          inputLocked.value = false
          pendingConfirm.value = false
        },
      },
      abortController.signal,
    )
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = err instanceof Error ? err.message : String(err)
    errorBanner.value = msg
    inputLocked.value = false
    pendingConfirm.value = false
  } finally {
    loading.value = false
    if (!awaitingSuggestionConfirm.value) {
      void tryShowConfirm()
    }
  }
}

function onInputActivity(value: string) {
  if (awaitingSuggestionConfirm.value && value.trim()) {
    clearToastTimer()
  }
}

function onConfirm() {
  showConfirm.value = false
  pendingConfirm.value = false
  pendingSkillCreateConfirm.value = false
  analysisQueue.resume()
  handleSend('是')
}

function onSkillBuildFinish() {
  if (skillBuildPendingFinish.value) return
  skillBuildPendingFinish.value = true
  beginSkillBuildExit()
  window.setTimeout(async () => {
    closeSkillBuild()
    skillBuildPendingFinish.value = false
    panelLayout.value = 'single'
    resetAbsorption()
    await initSession()
  }, 650)
}

async function onReturnHome() {
  analysisRunKey.value += 1
  await initSession()
}

async function onDeny() {
  showConfirm.value = false
  pendingConfirm.value = false
  pendingSkillCreateConfirm.value = false
  presentationPause.reset()
  analysisQueue.reset()
  resetSkillEventBuffer()
  await handleSend('否')
}

let unbindPresentationPause: (() => void) | null = null

onMounted(async () => {
  unbindPresentationPause = presentationPause.bindSpaceKey(
    () => docked.value && isPresentationPauseActive(),
    () => inputLocked.value,
  )

  try {
    await checkHealth()
    await initSession()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorBanner.value = `无法连接后端: ${msg}`
  }
})

onUnmounted(() => {
  unbindPresentationPause?.()
  unbindPresentationPause = null
})
</script>

<template>
  <div class="app-shell">
    <WorkbenchLayout
      ref="workbenchRef"
      :presentation="presentation.state"
      :map-actions="mapActions"
      :process-steps="processSteps"
      :panel-mode="panelMode"
      :conversation="conversationTurns"
      :missing-fields="missingFields"
      :process-active="loading || pendingConfirm"
      :docked="docked"
      :input-locked="inputLocked"
      :analysis-terminal="analysisTerminalMode"
      :loading="loading"
      :follow-up-bubble="followUpBubble"
      :map-toast="mapToast"
      :show-confirm="showConfirm"
      :confirm-message="confirmMessage"
      :error-banner="errorBanner"
      :hide-input-dock="hideInputDock"
      :channelization-active="channelizationActive"
      :analysis-run-key="analysisRunKey"
      :panel-layout="panelLayout"
      :absorption-state="absorptionState"
      :skill-build-state="skillBuildState"
      :voice-enabled="voice.enabled.value"
      :voice-playing="voice.playing.value"
      :presentation-paused="presentationPause.paused.value"
      :suggestion-confirm-banner="suggestionConfirmBanner"
      :presentation-layers="presentationSequence.layers.value"
      :focus-step-index="presentationSequence.focusStepIndex.value"
      :runtime-metrics-unlocked="runtimeMetricsUnlocked"
      :leaderboard-refresh-key="leaderboardRefreshKey"
      @toggle-voice="voice.toggleEnabled()"
      @channelization-active="channelizationActive = $event"
      @send="handleSend"
      @input-activity="onInputActivity"
      @toggle-step="toggleStep"
      @toggle-details="toggleDetails"
      @toggle-process="presentation.toggleProcessPanel()"
      @toggle-timing-ring="presentation.toggleTimingRingMini()"
      @close-timing-ring="presentation.closeTimingRingMini()"
      @toggle-corridor-wave="presentation.toggleCorridorWaveMini()"
      @close-corridor-wave="presentation.closeCorridorWaveMini()"
      @confirm="onConfirm"
      @deny="onDeny"
      @return-home="onReturnHome"
      @select-skill-file="selectSkillFile"
      @skill-build-finish="onSkillBuildFinish"
      @corridor-select="handleCorridorSelect"
      @upstream-narration="handleUpstreamNarration"
    />
    <ExperienceAbsorptionToast
      :toasts="absorptionToasts.toasts.value"
      @dismiss="absorptionToasts.dismiss"
    />
  </div>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  height: 100%;
  font-family:
    'PingFang SC',
    'Hiragino Sans GB',
    'Microsoft YaHei',
    'Courier New',
    monospace,
    system-ui,
    -apple-system,
    sans-serif;
  background: #020810;
}

.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #020810;
}
</style>
