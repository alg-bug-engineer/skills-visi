<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { checkHealth, createSession, sendMessageStream } from './api/client'
import WorkbenchLayout from './components/workbench/WorkbenchLayout.vue'
import { STEP_INDICES, STEP_PAUSE_MS } from './constants'
import { usePresentation } from './composables/usePresentation'
import { useUnderstandingProcess } from './composables/useUnderstandingProcess'
import { useSkillBuildProcess } from './composables/useSkillBuildProcess'
import { useExperienceAbsorption } from './composables/useExperienceAbsorption'
import { useVoiceNarration } from './composables/useVoiceNarration'
import { SKILL_BUILD_STAGES } from './types/skillBuild'
import type { ChatMessage, MessageResponse, StepRecord } from './types/api'
import type { ProblemEvidence, QuantitativeConstraints } from './types/evidence'
import type { CognitionPayload, IntersectionLink, MapActionEvent } from './types/map'
import type { CorridorIntersectionItem } from './types/corridor'
import type { GovernanceSuggestionPayload } from './types/presentation'
import { AnalysisQueue } from './utils/analysisQueue'
import { highlightDirsForGroup } from './utils/evidencePresentation'
import { parseHighlightTurn } from './utils/cognitionChannelAdapter'
import { buildEvidenceListItems } from './utils/channelizationCopy'
import { VOICE_GUIDE } from './services/voiceCueTemplates'
import { processStepPhase, resolveProcessStepVoice } from './services/voiceStepSync'
import { ABSORPTION_STAGE_VOICE } from './types/voice'
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
const mapActions = ref<MapActionEvent[]>([])
const showConfirm = ref(false)
const confirmMessage = ref('是否将此诊断固化为路口 Skill？')
const pendingConfirm = ref(false)
const mapToast = ref<string | null>(null)
const awaitingSuggestionConfirm = ref(false)
const channelizationActive = ref(false)
const analysisRunKey = ref(0)

const mapStageRef = ref<InstanceType<typeof MapStage> | null>(null)
const workbenchRef = ref<InstanceType<typeof WorkbenchLayout> | null>(null)

const PAIRED_NARRATION_PHASES = new Set([
  'traffic',
  'direction',
  'granularity',
  'timing',
  'corridor',
  'external',
  'saturation',
  'imbalance',
  'rule',
  'conclusion',
])
let pendingNarration: MapActionEvent | null = null
let lastUserContent = ''

type PanelMode = 'idle' | 'conversation' | 'analysis'
const panelMode = ref<PanelMode>('idle')
const sessionState = ref<string>('idle')
const conversationTurns = ref<ConversationTurn[]>([])
const missingFields = ref<string[]>([])
const followUpBubble = ref<string | null>(null)

const voice = useVoiceNarration()
const lastIntersectionName = ref<string | null>(null)
const voiceSentForStep = new Set<number>()

function rememberIntersectionName(name: string) {
  const trimmed = name.trim()
  if (!trimmed) return
  lastIntersectionName.value = trimmed
  handleProcessStepVoice(STEP_INDICES.INTERSECTION)
}

function handleProcessStepVoice(stepIndex: number) {
  if (!voice.enabled.value || voiceSentForStep.has(stepIndex)) return
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

const {
  steps: processSteps,
  enqueue: enqueueProcess,
  reset: resetProcess,
  toggleStep,
  whenIdle: whenProcessIdle,
} = useUnderstandingProcess({
  onStepStart(stepIndex) {
    handleProcessStepVoice(stepIndex)
  },
  onStepComplete(stepIndex) {
    presentation.revealInsightsForProcessStep(stepIndex)
  },
})

const {
  state: skillBuildState,
  applyEvent: applySkillBuildEvent,
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

/** 渠化全屏或技能固化/经验吸收演示时隐藏输入框，避免遮挡左侧终端 */
const hideInputDock = computed(
  () =>
    skillBuildState.visible ||
    absorptionState.active ||
    (channelizationActive.value &&
      inputLocked.value &&
      !showConfirm.value &&
      !followUpBubble.value &&
      !awaitingSuggestionConfirm.value),
)

const analysisQueue = new AnalysisQueue()
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
}

function formatEvidenceStepText(data: Record<string, unknown>): string {
  const items = buildEvidenceListItems(data as ProblemEvidence)
  return items.map((item) => `· ${item}`).join('\n')
}

function skillStageLabel(stage: string): string | null {
  return SKILL_BUILD_STAGES.find((s) => s.key === stage)?.label ?? null
}

function handleSkillAbsorptionEvent(event: import('./types/skillAbsorption').SkillAbsorptionEvent) {
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

function handleSkillBuildEvent(event: import('./types/skillBuild').SkillBuildEvent) {
  applySkillBuildEvent(event)
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

function pushMapAction(action: MapActionEvent) {
  mapActions.value.push(action)
}

function clearToastTimer() {
  if (toastTimer) {
    window.clearTimeout(toastTimer)
    toastTimer = null
  }
}

function showMapToast(message: string, visibleMs = 15000) {
  mapToast.value = message
  clearToastTimer()
  toastTimer = window.setTimeout(() => {
    mapToast.value = null
    toastTimer = null
  }, visibleMs)
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
  analysisQueue.pause()
  showMapToast(message)
}

function queueSuggestionConfirmPause(message: string) {
  if (suggestionConfirmQueued || awaitingSuggestionConfirm.value) return
  suggestionConfirmQueued = true
  docked.value = true
  analysisQueue.enqueue(async () => {
    suggestionConfirmQueued = false
    await revealSuggestionStep(message)
    startSuggestionConfirmPause(message)
  }, STEP_PAUSE_MS)
}

function stopSuggestionConfirmPause({ resumeQueue = true } = {}) {
  suggestionConfirmQueued = false
  awaitingSuggestionConfirm.value = false
  pendingConfirm.value = false
  clearToastTimer()
  mapToast.value = null
  if (resumeQueue) analysisQueue.resume()
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
  await whenProcessIdle()
  pushSkillStep(message)
  await whenProcessIdle()
}

async function revealSuggestionStep(message: string) {
  await whenProcessIdle()
  enqueueProcess(STEP_INDICES.SUGGESTION, message, true)
  await whenProcessIdle()
}

async function finalizeDiagnosisUi(result: MessageResponse) {
  if (panelMode.value !== 'analysis') return

  if (isSuggestionGenerateConfirm(result)) {
    queueSuggestionConfirmPause(result.reply.content || confirmMessage.value)
    return
  }

  await analysisQueue.whenIdle()
  await whenProcessIdle()

  if (!hasSkillStep()) {
    const skillAction = result.meta?.skill_action as string | undefined
    if (result.state === 'awaiting_confirm') {
      await revealSkillStep(
        confirmMessage.value ||
          '是否将此诊断固化为路口 Skill？回复「是」确认固化，「否」结束本次会话。',
      )
    } else if (skillAction === 'verified') {
      await revealSkillStep('Skill 校验通过：历史技能包与本次诊断结论一致，无需更新。')
    }
  }

  if (pendingConfirm.value) {
    showConfirm.value = true
    inputLocked.value = false
  } else if (result.state !== 'awaiting_confirm') {
    inputLocked.value = false
  }
}

async function tryShowConfirm() {
  if (
    !pendingConfirm.value ||
    showConfirm.value ||
    awaitingSuggestionConfirm.value ||
    suggestionConfirmQueued
  ) {
    return
  }
  await analysisQueue.whenIdle()
  await whenProcessIdle()
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
  enqueueProcess(STEP_INDICES.UNDERSTAND, intro)
}

function prepareNewAnalysisRun(userContent: string) {
  stopSuggestionConfirmPause()
  analysisQueue.reset()
  resetProcess()
  steps.value = []
  presentation.prepareNewAnalysisRun()
  mapActions.value = []
  pendingNarration = null
  analysisRunKey.value += 1
  lastIntersectionName.value = null
  voiceSentForStep.clear()
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
  if (action.highlight_dirs?.length) {
    presentation.setHighlightDirs(action.highlight_dirs)
  }
  if (action.highlight_turn) {
    presentation.setHighlightTurn(
      parseHighlightTurn(action.highlight_turn),
    )
  } else if (action.phase && action.phase !== 'granularity') {
    presentation.setHighlightTurn(null)
  }
  if (action.phase) {
    presentation.setPhase(action.phase as import('./types/presentation').PipelinePhase)
  }
  if (action.hud) {
    presentation.setHud(action.hud)
  }
}

function handleNarration(action: MapActionEvent) {
  const text = action.text ?? ''
  if (!text) return

  if (action.phase === 'links' || action.phase === 'channelization') {
    enqueueProcess(STEP_INDICES.COGNITION, text)
    return
  }
  if (
    action.phase === 'traffic' ||
    action.phase === 'direction' ||
    action.phase === 'granularity' ||
    action.phase === 'timing' ||
    action.phase === 'corridor' ||
    action.phase === 'external' ||
    action.phase === 'saturation' ||
    action.phase === 'imbalance'
  ) {
    const prefix = action.title ? `${action.title}：` : ''
    enqueueProcess(STEP_INDICES.DATA_FETCH, `${prefix}${text}`, true)
    return
  }
  if (action.phase === 'rule') {
    presentation.setPhase('rule')
    enqueueProcess(STEP_INDICES.RULE, text)
    return
  }
  if (action.phase === 'conclusion') {
    presentation.setPhase('conclusion')
    patchSuggestionPayload(action.suggestion)
    enqueueProcess(STEP_INDICES.SUGGESTION, text)
    return
  }
  if (action.phase === 'locate') {
    enqueueProcess(STEP_INDICES.INTERSECTION, text, true)
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
      const inter = action.intersection
      if (inter?.name) {
        rememberIntersectionName(inter.name)
        enqueueProcess(STEP_INDICES.INTERSECTION, `已定位路口：${inter.name}`, true, true)
      }
      presentation.setPhase('locate')
      updateCognitionFromAction(action)
      pushMapAction(action)
      return
    }

    if (action.action === 'highlight_links') {
      updateCognitionFromAction(action)
      presentation.setHighlightTurn(null)
      presentation.setPhase('links')
      enqueueProcess(STEP_INDICES.COGNITION, formatLinksText(action.links ?? []))
      pushMapAction(action)
      return
    }

    if (action.action === 'update_metrics') {
      updateCognitionFromAction(action)
      const ev = action.evaluation as Record<string, unknown> | undefined
      const tf = action.traffic_flow as Record<string, unknown> | undefined
      if (ev || tf) {
        const metrics: Array<{ label: string; value: string; severity?: string }> = []
        const sat = tf?.saturation_rate ?? ev?.saturation_rate
        if (sat != null) {
          const n = Number(sat)
          metrics.push({
            label: '饱和度',
            value: `${Number(sat).toFixed(2)}`,
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
        const spread = tf?.turn_saturation_spread
        if (spread != null) {
          metrics.push({ label: '转向极差', value: Number(spread).toFixed(2) })
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
      if (narration) {
        await whenProcessIdle()
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

    if (action.action === 'confirm_bubble') {
      if (action.action_type === 'generate_suggestion') {
        const message = action.message ?? '问题诊断成立，是否需要生成治理建议？'
        suggestionConfirmQueued = false
        await revealSuggestionStep(message)
        startSuggestionConfirmPause(message)
        return
      }
      confirmMessage.value = action.message ?? confirmMessage.value
      await revealSkillStep(
        action.message ??
          '是否将此诊断固化为路口 Skill？回复「是」确认固化，「否」结束本次会话。',
      )
      pendingConfirm.value = true
      showConfirm.value = true
      inputLocked.value = false
      return
    }

    if (action.action === 'skill_verify') {
      await revealSkillStep(
        action.message ?? 'Skill 校验通过：历史技能包与本次诊断结论一致，无需更新。',
      )
      inputLocked.value = false
      return
    }

    pushMapAction(action)
  }, STEP_PAUSE_MS)
}

function handleProblemEvidenceStep(data: Record<string, unknown>) {
  const text = formatEvidenceStepText(data)
  analysisQueue.enqueue(async () => {
    enqueueProcess(STEP_INDICES.PROBLEM_EVIDENCE, text)

    const partial = data as unknown as ProblemEvidence & {
      quantitative_constraints?: QuantitativeConstraints
    }
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
      const dirs = focused.flatMap((d) => highlightDirsForGroup(d.group))
      presentation.setHighlightDirs(dirs)
    }
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
        const prefix = data.matched ? '📚 ' : 'ℹ️ '
        enqueueProcess(STEP_INDICES.INTERSECTION, `${prefix}${notice}`, true, true)
      }, STEP_PAUSE_MS)
    }
    return
  }

  if (event.step === 'intersection' && data.inter_name) {
    rememberIntersectionName(String(data.inter_name))
    analysisQueue.enqueue(async () => {
      enqueueProcess(STEP_INDICES.INTERSECTION, `路口匹配：${data.inter_name}`, true, true)
    }, STEP_PAUSE_MS)
  }

  if (event.step === 'problem_evidence') {
    handleProblemEvidenceStep(data)
    return
  }

  if (event.step === 'data_fetch') {
    const partial = data as {
      timing_profile?: ProblemEvidence['timing_profile']
      corridor_context?: ProblemEvidence['corridor_context']
      granularity?: { by_turn?: Array<{ label?: string; turn_saturation?: number }> }
    }
    if (partial.timing_profile || partial.corridor_context) {
      presentation.patchEvidence({
        ...(presentation.state.evidence ?? {}),
        timing_profile: partial.timing_profile ?? presentation.state.evidence?.timing_profile,
        corridor_context:
          partial.corridor_context ?? presentation.state.evidence?.corridor_context,
      } as ProblemEvidence)
    }
    const topTurn = partial.granularity?.by_turn?.[0]
    if (topTurn?.label) {
      const label = String(topTurn.label)
      const dirMatch = label.match(/[东南西北]/)
      const turnMatch = label.match(/左|直|右|调/)
      if (dirMatch && turnMatch) {
        presentation.setHighlightTurn({
          dir: dirMatch[0],
          turn: turnMatch[0],
          label,
          saturation: topTurn.turn_saturation ?? null,
        })
      }
    }
    return
  }

  if (event.step === 'rule_engine') {
    if (data.flow_timing_governance) {
      presentation.patchFlowTimingGovernance(
        data.flow_timing_governance as import('./types/evidence').FlowTimingGovernance,
      )
      presentation.setPhase('rule')
      analysisQueue.enqueue(async () => {
        const gov = data.flow_timing_governance as { summary?: string }
        enqueueProcess(
          STEP_INDICES.RULE,
          gov.summary ?? '四维信控诊断完成',
          true,
          true,
        )
      }, STEP_PAUSE_MS)
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
  analysisQueue.reset()
  resetProcess()
  resetSkillBuild()
  resetAbsorption()
  panelLayout.value = 'single'
  presentation.reset()
  skillBuildPendingFinish.value = false
  loading.value = false
  inputLocked.value = false
  docked.value = false
  showConfirm.value = false
  pendingConfirm.value = false
  awaitingSuggestionConfirm.value = false
  mapToast.value = null
  mapActions.value = []
  pendingNarration = null
  suggestionConfirmQueued = false
  lastIntersectionName.value = null
  voiceSentForStep.clear()
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
          handleSkillBuildEvent(event)
        },
        onSkillAbsorption: (event) => {
          handleSkillAbsorptionEvent(event)
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
            if (isSuggestionGenerateConfirm(result)) {
              docked.value = true
            }
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

async function onDeny() {
  showConfirm.value = false
  pendingConfirm.value = false
  analysisQueue.reset()
  await handleSend('否')
}

onMounted(async () => {
  try {
    await checkHealth()
    await initSession()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorBanner.value = `无法连接后端: ${msg}`
  }
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
      @toggle-voice="voice.toggleEnabled()"
      @channelization-active="channelizationActive = $event"
      @send="handleSend"
      @input-activity="onInputActivity"
      @toggle-step="toggleStep"
      @toggle-process="presentation.toggleProcessPanel()"
      @toggle-timing-ring="presentation.toggleTimingRingMini()"
      @close-timing-ring="presentation.closeTimingRingMini()"
      @toggle-corridor-wave="presentation.toggleCorridorWaveMini()"
      @close-corridor-wave="presentation.closeCorridorWaveMini()"
      @confirm="onConfirm"
      @deny="onDeny"
      @select-skill-file="selectSkillFile"
      @skill-build-finish="onSkillBuildFinish"
      @corridor-select="handleCorridorSelect"
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
