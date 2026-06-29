import { reactive } from 'vue'
import type { FlowTimingGovernance, ProblemEvidence, QuantitativeConstraints } from '../types/evidence'
import type { CognitionPayload, MapSceneHud } from '../types/map'
import type { CorridorIntersectionItem } from '../types/corridor'
import type { DataInsight, DataInsightMetric, InsightCardEntry } from '../types/insight'
import { STEP_INDICES } from '../constants'
import { RUNTIME_METRIC_SKIP_LABELS } from '../utils/narrativeStack'
import {
  CORRIDOR_WAVE_AUTO_PHASES,
  TIMING_RING_AUTO_PHASES,
  createInitialPresentation,
  type PipelinePhase,
  type PresentationState,
  type RuntimeMetrics,
  type HighlightTurn,
  type GovernanceSuggestionPayload,
} from '../types/presentation'

const CARD_ORDER = [
  'data',
  'chronic',
  'evidence',
  'timing',
  'governance',
  'corridor',
  'external',
  'constraints',
] as const

function mergeMetrics(
  target: DataInsightMetric[],
  incoming: DataInsightMetric[],
): DataInsightMetric[] {
  const map = new Map(target.map((m) => [m.label, m]))
  for (const m of incoming) {
    map.set(m.label, m)
  }
  return Array.from(map.values())
}

function cardOrderIndex(kind: InsightCardEntry['kind']): number {
  const idx = (CARD_ORDER as readonly string[]).indexOf(kind)
  return idx < 0 ? 99 : idx
}

function sortInsightCards(cards: PresentationState['insightCards']) {
  cards.sort((a, b) => cardOrderIndex(a.kind) - cardOrderIndex(b.kind))
}

function upsertInsightCard<T extends InsightCardEntry['kind']>(
  cards: PresentationState['insightCards'],
  kind: T,
  _id: string,
  payload: Extract<InsightCardEntry, { kind: T }>,
) {
  const idx = cards.findIndex((c) => c.kind === kind)
  if (idx >= 0) {
    cards[idx] = payload
    return
  }
  cards.push(payload)
  sortInsightCards(cards)
}

export function usePresentation() {
  const state = reactive<PresentationState>(createInitialPresentation())

  function clearInsights() {
    state.insightCards.length = 0
    state.evidence = null
    state.constraints = null
    state.flowTimingGovernance = null
    state.governanceSuggestion = null
    state.dataInsightBuffer = null
    state.hud = null
    state.runtimeMetrics = null
    state.highlightTurn = null
    state.corridorScan = null
    state.focusedDirs = []
    state.protectedDirs = []
    state.revealedInsightSteps = {
      data: false,
      evidence: false,
      constraints: false,
      extended: false,
      governance: false,
      suggestionNote: false,
    }
  }

  /** 同页二次分析：清空展示态，避免上一轮证据/横幅残留遮挡 */
  function prepareNewAnalysisRun() {
    clearInsights()
    state.phase = 'idle'
    state.cognition = null
    state.corridorScan = null
    state.highlightDirs = []
    state.timingRingMiniOpen = false
    state.timingRingMiniDismissed = false
    state.corridorWaveMiniOpen = false
    state.corridorWaveMiniDismissed = false
  }

  function reset() {
    Object.assign(state, createInitialPresentation())
  }

  function setPhase(phase: PipelinePhase) {
    state.phase = phase
    if (phase !== 'direction') {
      state.protectedDirs = []
    }

    if (TIMING_RING_AUTO_PHASES.includes(phase)) {
      if (
        !state.timingRingMiniDismissed &&
        state.evidence?.timing_profile?.ring_diagram?.available
      ) {
        state.timingRingMiniOpen = true
      }
    } else if (phase === 'rule' || phase === 'conclusion') {
      state.timingRingMiniOpen = false
    }

    if (CORRIDOR_WAVE_AUTO_PHASES.includes(phase)) {
      if (
        !state.corridorWaveMiniDismissed &&
        (state.evidence?.corridor_context?.in_corridor ||
          (state.evidence?.corridor_context?.corridor_nodes?.length ?? 0) > 0)
      ) {
        state.corridorWaveMiniOpen = true
      }
    } else if (phase === 'rule' || phase === 'conclusion') {
      state.corridorWaveMiniOpen = false
    }
  }

  /** 累积运行数据，不立刻展示卡片 */
  function mergeDataInsight(insight: DataInsight) {
    if (!state.dataInsightBuffer) {
      state.dataInsightBuffer = {
        title: insight.title,
        icon: insight.icon,
        metrics: [...insight.metrics],
      }
      return
    }
    const buf = state.dataInsightBuffer
    if (insight.title) buf.title = insight.title
    if (insight.icon) buf.icon = insight.icon
    buf.metrics = mergeMetrics(buf.metrics, insight.metrics)
  }

  function revealDataCard() {
    if (!state.dataInsightBuffer?.metrics.length) return
    const idx = state.insightCards.findIndex((c) => c.kind === 'data')
    if (idx >= 0) {
      const card = state.insightCards[idx]
      if (card.kind === 'data') {
        card.insight.title = state.dataInsightBuffer.title
        card.insight.icon = state.dataInsightBuffer.icon
        card.insight.metrics = mergeMetrics(
          card.insight.metrics,
          state.dataInsightBuffer.metrics,
        )
      }
    } else {
      state.insightCards.push({
        id: 'data',
        kind: 'data',
        insight: {
          title: state.dataInsightBuffer.title,
          icon: state.dataInsightBuffer.icon,
          metrics: [...state.dataInsightBuffer.metrics],
        },
      })
      sortInsightCards(state.insightCards)
    }
    state.revealedInsightSteps.data = true
  }

  function patchEvidence(evidence: ProblemEvidence | null) {
    state.evidence = evidence
    if (evidence?.by_direction) {
      state.focusedDirs = evidence.by_direction
        .filter((d) => d.focused)
        .map((d) => d.group)
    }
    if (evidence?.timing_profile?.ring_diagram?.available && !state.timingRingMiniDismissed) {
      if (TIMING_RING_AUTO_PHASES.includes(state.phase)) {
        state.timingRingMiniOpen = true
      }
    }
    if (
      (evidence?.corridor_context?.in_corridor ||
        (evidence?.corridor_context?.corridor_nodes?.length ?? 0) > 0) &&
      !state.corridorWaveMiniDismissed &&
      CORRIDOR_WAVE_AUTO_PHASES.includes(state.phase)
    ) {
      state.corridorWaveMiniOpen = true
    }
    if (evidence && state.revealedInsightSteps.evidence) {
      revealExtendedCards(evidence)
    }
  }

  function revealExtendedCards(evidence: ProblemEvidence) {
    const chronic = evidence.chronic
    const hasChronicData =
      Boolean(chronic?.is_chronic) &&
      ((chronic?.congested_days ?? 0) > 0 || (chronic?.congested_dates?.length ?? 0) > 0)
    if (hasChronicData) {
      upsertInsightCard(state.insightCards, 'chronic', 'chronic', {
        id: 'chronic',
        kind: 'chronic',
        evidence,
      })
    }
    state.revealedInsightSteps.extended = true
  }

  function revealEvidenceCard() {
    if (!state.evidence) return
    revealExtendedCards(state.evidence)
    state.revealedInsightSteps.evidence = true
  }

  function patchConstraints(constraints: QuantitativeConstraints | null) {
    state.constraints = constraints
  }

  function revealConstraintsCard() {
    if (!state.constraints) return
    state.revealedInsightSteps.constraints = true
  }

  function setCognition(cognition: CognitionPayload | null) {
    state.cognition = cognition
  }

  function setHud(hud: MapSceneHud | null) {
    state.hud = hud
    if (hud?.metrics?.length) {
      mergeDataInsight({
        title: hud.title ?? '运行数据',
        icon: hud.icon,
        metrics: hud.metrics
          .filter((m) => !RUNTIME_METRIC_SKIP_LABELS.has(m.label))
          .map((m) => ({
          label: m.label,
          value: m.value,
          severity: m.severity,
        })),
      })
    }
  }

  function setHighlightDirs(dirs: string[]) {
    state.highlightDirs = [...dirs]
  }

  function setProtectedGroups(groups: string[]) {
    state.protectedDirs = [...groups]
  }

  function setHighlightTurn(turn: HighlightTurn | null) {
    state.highlightTurn = turn
  }

  function patchRuntimeMetrics(metrics: RuntimeMetrics | null) {
    if (!metrics) return
    state.runtimeMetrics = { ...(state.runtimeMetrics ?? {}), ...metrics }
  }

  function openTimingRingMini() {
    state.timingRingMiniOpen = true
    state.timingRingMiniDismissed = false
  }

  function closeTimingRingMini() {
    state.timingRingMiniOpen = false
    state.timingRingMiniDismissed = true
  }

  function toggleTimingRingMini() {
    if (state.timingRingMiniOpen) closeTimingRingMini()
    else openTimingRingMini()
  }

  function openCorridorWaveMini() {
    state.corridorWaveMiniOpen = true
    state.corridorWaveMiniDismissed = false
  }

  function closeCorridorWaveMini() {
    state.corridorWaveMiniOpen = false
    state.corridorWaveMiniDismissed = true
  }

  function toggleCorridorWaveMini() {
    if (state.corridorWaveMiniOpen) closeCorridorWaveMini()
    else openCorridorWaveMini()
  }

  function toggleProcessPanel() {
    state.processCollapsed = !state.processCollapsed
  }

  function patchFlowTimingGovernance(governance: FlowTimingGovernance | null) {
    state.flowTimingGovernance = governance
  }

  function patchGovernanceSuggestion(suggestion: GovernanceSuggestionPayload | null) {
    if (!suggestion) return
    state.governanceSuggestion = {
      ...(state.governanceSuggestion ?? {}),
      ...suggestion,
    }
  }

  function revealSuggestionNote() {
    if (!state.governanceSuggestion?.narrative) return
    state.revealedInsightSteps.suggestionNote = true
  }

  function revealGovernanceCard() {
    if (!state.flowTimingGovernance) return
    state.revealedInsightSteps.governance = true
  }

  function revealInsightsForProcessStep(stepIndex: number) {
    if (stepIndex === STEP_INDICES.DATA_FETCH) {
      revealDataCard()
    } else if (stepIndex === STEP_INDICES.PROBLEM_EVIDENCE) {
      revealEvidenceCard()
      revealConstraintsCard()
    } else if (stepIndex === STEP_INDICES.RULE) {
      revealGovernanceCard()
    } else if (stepIndex === STEP_INDICES.SUGGESTION) {
      revealSuggestionNote()
    }
  }

  function setCorridorScan(payload: {
    lineName: string
    timePeriodLabel: string
    intersections: CorridorIntersectionItem[]
    focusInterId?: string | null
  }) {
    const focus = payload.focusInterId ?? null
    state.corridorScan = {
      lineName: payload.lineName,
      timePeriodLabel: payload.timePeriodLabel,
      intersections: payload.intersections,
      focusInterId: focus,
      selectedInterId: focus,
    }
    state.phase = 'corridor_scan'
  }

  function selectCorridorIntersection(interId: string) {
    if (!state.corridorScan) return
    state.corridorScan.selectedInterId = interId
  }

  function clearCorridorScan() {
    state.corridorScan = null
  }

  return {
    state,
    clearInsights,
    prepareNewAnalysisRun,
    reset,
    setPhase,
    mergeDataInsight,
    revealDataCard,
    patchEvidence,
    revealEvidenceCard,
    patchConstraints,
    revealConstraintsCard,
    patchFlowTimingGovernance,
    patchGovernanceSuggestion,
    revealSuggestionNote,
    revealGovernanceCard,
    revealInsightsForProcessStep,
    setCognition,
    setHud,
    setHighlightDirs,
    setProtectedGroups,
    setHighlightTurn,
    patchRuntimeMetrics,
    openTimingRingMini,
    closeTimingRingMini,
    toggleTimingRingMini,
    openCorridorWaveMini,
    closeCorridorWaveMini,
    toggleCorridorWaveMini,
    toggleProcessPanel,
    setCorridorScan,
    selectCorridorIntersection,
    clearCorridorScan,
  }
}

export type PresentationApi = ReturnType<typeof usePresentation>
