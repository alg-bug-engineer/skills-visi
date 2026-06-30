import type { FlowTimingGovernance, ProblemEvidence, QuantitativeConstraints } from './evidence'
import type { CognitionPayload, MapSceneHud } from './map'
import type { CorridorScanState } from './corridor'
import type { CaseScenario, ExperienceSedimentItem } from './experience'
import type { InsightCardEntry } from './insight'
import { createInsightCards as mkCards } from './insight'

export type PipelinePhase =
  | 'idle'
  | 'conversation'
  | 'corridor_scan'
  | 'locate'
  | 'links'
  | 'channelization'
  | 'traffic'
  | 'direction'
  | 'saturation'
  | 'granularity'
  | 'timing'
  | 'corridor'
  | 'external'
  | 'imbalance'
  | 'evidence'
  | 'constraints'
  | 'rule'
  | 'conclusion'
  | 'skill'

/** 渠化主舞台：定位后自然切入，替代右下角小窗 */
export const CHANNELIZATION_OVERLAY_PHASES: PipelinePhase[] = [
  'links',
  'channelization',
  'traffic',
  'direction',
  'granularity',
  'saturation',
  'imbalance',
  'timing',
  'corridor',
  'external',
]

/** @deprecated 使用 CHANNELIZATION_OVERLAY_PHASES */
export const CHANNELIZATION_AUTO_PHASES: PipelinePhase[] = CHANNELIZATION_OVERLAY_PHASES

/** 配时环图小窗 */
export const TIMING_RING_AUTO_PHASES: PipelinePhase[] = ['timing', 'granularity', 'saturation', 'imbalance']

/** 干线绿波小窗 */
export const CORRIDOR_WAVE_AUTO_PHASES: PipelinePhase[] = ['corridor', 'external']

/**
 * @deprecated 底部四向指标条改由 useChannelFooterLayout 粘性揭示（direction 起常驻）
 */
export const METRIC_STRIP_PHASES: PipelinePhase[] = [
  'direction',
  'saturation',
  'imbalance',
  'rule',
  'conclusion',
  'evidence',
]

/** 仅展示渠化结构，不叠加运行指标/排队/饱和度高亮 */
export const COGNITION_STRUCTURE_PHASES: PipelinePhase[] = ['locate', 'links', 'channelization']

export interface GovernanceSuggestionPayload {
  narrative?: string
  delta_seconds?: number
  direction?: string
  rule_id?: string
  /** 治理建议的可溯源依据（案例/经验），可跳转案例库 */
  references?: import('./experience').SuggestionReference[]
}

export interface PresentationState {
  phase: PipelinePhase
  cognition: CognitionPayload | null
  evidence: ProblemEvidence | null
  constraints: QuantitativeConstraints | null
  flowTimingGovernance: FlowTimingGovernance | null
  /** 治理建议正文，生成后常驻渠化图右上角 */
  governanceSuggestion: GovernanceSuggestionPayload | null
  /** 运行数据缓冲，待「获取数据」步骤完成后再展示为单卡 */
  dataInsightBuffer: import('./insight').DataInsight | null
  insightCards: InsightCardEntry[]
  revealedInsightSteps: {
    data: boolean
    /** 左侧叙事卡「运行数据」区块：理解过程进入「运行数据」步骤后揭示 */
    runtimePanel: boolean
    evidence: boolean
    constraints: boolean
    extended: boolean
    governance: boolean
    /** 治理建议正文生成后展示渠化图右上角卡片，此后常驻 */
    suggestionNote: boolean
  }
  highlightDirs: string[]
  protectedDirs: string[]
  focusedDirs: string[]
  hud: MapSceneHud | null
  channelizationMiniOpen: boolean
  channelizationMiniDismissed: boolean
  timingRingMiniOpen: boolean
  timingRingMiniDismissed: boolean
  corridorWaveMiniOpen: boolean
  corridorWaveMiniDismissed: boolean
  processCollapsed: boolean
  /** update_metrics 缓冲的整体运行指标，供渠化高亮在 evidence 到达前使用 */
  runtimeMetrics: RuntimeMetrics | null
  /** 多粒度阶段强调的转向，如西左转 */
  highlightTurn: HighlightTurn | null
  /** 干线扫描：左侧路口列表与选中态 */
  corridorScan: CorridorScanState | null
  /** 三级经验逐步沉淀（认知/诊断/方案），每步落库后点亮 */
  experienceSediment: ExperienceSedimentItem[]
  /** 本轮复用的历史经验高亮 badge */
  reusedExperience: string[]
  /** 同类场景专家治理经验 */
  caseExperience: CaseScenario[]
  /** 后端按问题类型推导的呈现维度：驱动「无关卡片/图层不出现」（空=未知，permissive） */
  activeDimensions: string[]
  /** 本轮诊断命中的问题类型（拥堵/溢出/空放/冲突，可叠加） */
  problemTypes: string[]
}

/**
 * 某呈现维度在当前问题下是否相关。
 * activeDimensions 为空（后端未下发/未知）时一律 permissive，避免误隐藏。
 */
export function isPresentationDimActive(
  activeDimensions: string[] | undefined | null,
  dim: string,
): boolean {
  if (!activeDimensions || activeDimensions.length === 0) return true
  return activeDimensions.includes(dim)
}

export interface RuntimeMetrics {
  saturation_rate?: number | null
  delay_index?: number | null
  imbalance_index?: number | null
  green_utilization?: number | null
}

export interface HighlightTurn {
  dir: string
  turn: string
  label?: string
  saturation?: number | null
}

export function createInitialPresentation(): PresentationState {
  return {
    phase: 'idle',
    cognition: null,
    evidence: null,
    constraints: null,
    flowTimingGovernance: null,
    governanceSuggestion: null,
    dataInsightBuffer: null,
    insightCards: mkCards(),
    revealedInsightSteps: {
      data: false,
      runtimePanel: false,
      evidence: false,
      constraints: false,
      extended: false,
      governance: false,
      suggestionNote: false,
    },
    highlightDirs: [],
    protectedDirs: [],
    focusedDirs: [],
    hud: null,
    channelizationMiniOpen: false,
    channelizationMiniDismissed: false,
    timingRingMiniOpen: false,
    timingRingMiniDismissed: false,
    corridorWaveMiniOpen: false,
    corridorWaveMiniDismissed: false,
    processCollapsed: false,
    runtimeMetrics: null,
    highlightTurn: null,
    corridorScan: null,
    experienceSediment: [],
    reusedExperience: [],
    caseExperience: [],
    activeDimensions: [],
    problemTypes: [],
  }
}

export function shouldShowChannelizationOverlay(
  phase: PipelinePhase,
  cognition: CognitionPayload | null,
): boolean {
  return Boolean(cognition?.arms?.length) && CHANNELIZATION_OVERLAY_PHASES.includes(phase)
}

export function shouldShowTimingRingMini(
  phase: PipelinePhase,
  state: Pick<
    PresentationState,
    'timingRingMiniOpen' | 'timingRingMiniDismissed' | 'evidence' | 'activeDimensions'
  >,
): boolean {
  const hasRing = Boolean(state.evidence?.timing_profile?.ring_diagram?.available)
  if (!hasRing) return false
  // 配时环图仅在当前问题用到「环图」维度时出现（如空放）；拥堵等不展示
  if (!isPresentationDimActive(state.activeDimensions, 'ring')) return false
  if (state.timingRingMiniDismissed && !state.timingRingMiniOpen) return false
  if (state.timingRingMiniOpen) return true
  return TIMING_RING_AUTO_PHASES.includes(phase)
}

export function shouldShowCorridorWaveMini(
  phase: PipelinePhase,
  state: Pick<PresentationState, 'corridorWaveMiniOpen' | 'corridorWaveMiniDismissed' | 'evidence'>,
): boolean {
  const corridor = state.evidence?.corridor_context
  const hasCorridor = Boolean(
    corridor?.in_corridor || (corridor?.corridor_nodes?.length ?? 0) > 0,
  )
  if (!hasCorridor) return false
  if (state.corridorWaveMiniDismissed && !state.corridorWaveMiniOpen) return false
  if (state.corridorWaveMiniOpen) return true
  return CORRIDOR_WAVE_AUTO_PHASES.includes(phase)
}
