/**
 * channelizationPhase.ts
 *
 * 阶段→标注调度（从 ChannelizationCanvas3D.applyPhaseHighlight 原样移植）。
 * 纯逻辑，作用于实现 PhaseHighlightTarget 的渠化层（AMap 版），便于单测。
 * 必须 1:1 复刻原早返语义，确保与 voice/presentation 时序一致。
 */
import type { CognitionPayload, MapSceneMarker } from '../types/map'
import type { ProblemEvidence } from '../types/evidence'
import type { HighlightTurn, PipelinePhase, RuntimeMetrics } from '../types/presentation'
import { COGNITION_STRUCTURE_PHASES, isPresentationDimActive } from '../types/presentation'
import {
  buildHighlightEvidence,
  highlightVerdict,
  turnCodeFromLabel,
  type ChannelQueueArm,
} from '../utils/cognitionChannelAdapter'
import {
  buildArmLabelsFromScene,
  buildArmLabelsFromDirectionGroups,
  buildArmLabelsFromEntranceLinks,
  buildArmLabelsFromQueue,
  buildRoleArmLabels,
  isPlaceholderLabelLine,
  parseSaturationFromLabelLine,
  saturationHintColor,
  saturationProblemHint,
} from '../utils/channelArmLabels'
import { highlightDirsForGroup, normalizeAxisFocusGroups, toAxisFocusGroup } from '../utils/evidencePresentation'
import { resolvePrimaryProblemType } from '../utils/runtimeMetricProfile'
import type { ArmSceneLabel, HighlightEvidence, TurnHighlightSpec } from './channelizationAmap'

export interface PhaseHighlightTarget {
  clearCheck(): void
  applyTurnHighlight(spec: TurnHighlightSpec): void
  applyTurnSaturationLabels(
    specs: Array<{ dir: string; turnCode: string; label: string; saturation: number }>,
  ): void
  applyCheckHighlight(indicatorId: string, verdict: string, evidence: HighlightEvidence): void
  applyDirectionRoleHighlight(focusDirs: string[], protectDirs: string[]): void
  applyArmSceneLabels(labels: ArmSceneLabel[]): void
  applyQueueLengthHighlight(queueArms: ChannelQueueArm[]): void
}

export interface PhaseHighlightParams {
  phase?: PipelinePhase
  cognition: CognitionPayload | null
  evidence?: ProblemEvidence | null
  runtimeMetrics?: RuntimeMetrics | null
  highlightTurn?: HighlightTurn | null
  highlightDirs?: string[]
  protectedDirs?: string[]
  sceneMarkers?: MapSceneMarker[]
  /** 每进口排队/饱和度数据，驱动渠化排队长度标签 */
  queueArms?: ChannelQueueArm[]
  /** 后端按问题类型推导的呈现维度，门控排队等图层是否相关 */
  activeDimensions?: string[]
  problemTypes?: string[]
  /** 运行数据步骤已揭示后才展示排队/饱和度等运行指标标注 */
  allowRuntimeMetrics?: boolean
}

const ARM_LABEL_PHASES: PipelinePhase[] = [
  'direction',
  'traffic',
  'saturation',
  'granularity',
  'timing',
  'imbalance',
]

/** 仅在这些阶段于渠化地图上展示饱和度数值（避免 traffic 与左侧面板重复） */
const SATURATION_ON_MAP_PHASES: PipelinePhase[] = ['direction', 'saturation']

function isSaturationLabelLine(line2: string): boolean {
  const t = line2.trim()
  return (
    /^饱和[\d.]+/.test(t) ||
    /^饱和度 /.test(t) ||
    /^[\d.]+$/.test(t)
  )
}

function stripSaturationFromLabels(labels: ArmSceneLabel[]): ArmSceneLabel[] {
  return labels
    .map((l) => {
      const line2Raw = l.line2 ?? ''
      if (!isSaturationLabelLine(line2Raw)) {
        return isPlaceholderLabelLine(line2Raw) ? null : l
      }
      const line2 = line2Raw.replace(/^饱和[\d.]+ · /, '').trim()
      if (!line2 || isSaturationLabelLine(line2) || isPlaceholderLabelLine(line2)) {
        return null
      }
      return { ...l, line2 }
    })
    .filter((l): l is ArmSceneLabel => l != null && Boolean(l.line1 || l.line2?.trim()))
}

function enrichSaturationHints(labels: ArmSceneLabel[]): ArmSceneLabel[] {
  return labels
    .map((l) => {
      const line2 = l.line2 ?? ''
      const sat = parseSaturationFromLabelLine(line2)
      if (sat == null) return isPlaceholderLabelLine(line2) ? null : l
      return {
        ...l,
        line2: saturationProblemHint(sat),
        colorHex: saturationHintColor(sat),
      }
    })
    .filter((l): l is ArmSceneLabel => l != null && Boolean(l.line1 || l.line2?.trim()))
}

/** 关注/保护高亮与臂标在运行数据相关阶段持续展示，避免一闪而过。 */
const ROLE_HIGHLIGHT_PHASES: PipelinePhase[] = ['direction', 'traffic', 'saturation', 'granularity']

/** traffic 展示排队；direction/saturation 在饱和度提示旁可叠加排队长度 */
const QUEUE_LABEL_PHASES: PipelinePhase[] = ['traffic', 'direction', 'saturation']

function sceneMarkersForPhase(phase: PipelinePhase, markers: MapSceneMarker[]): MapSceneMarker[] {
  if (phase === 'direction') return markers
  return markers.filter((m) => m.variant !== 'protected' && !(m.title?.includes('保护')))
}

function armLabelsForPhase(
  phase: PipelinePhase,
  sceneMarkers: MapSceneMarker[],
  cognition: CognitionPayload | null,
  queueArms: ChannelQueueArm[] = [],
  activeDimensions?: string[],
  problemTypes: string[] = [],
  highlightDirs: string[] = [],
  protectedDirs: string[] = [],
  imbalanceIndex?: number | null,
): ArmSceneLabel[] {
  if (!ARM_LABEL_PHASES.includes(phase)) return []
  if (highlightDirs.length || protectedDirs.length) {
    const role = buildRoleArmLabels(
      highlightDirs,
      protectedDirs,
      cognition,
      queueArms,
      imbalanceIndex,
      problemTypes,
    )
    if (role.length) return role
  }
  const base = baseArmLabels(phase, sceneMarkers, cognition)
  return mergeQueueLabels(phase, base, queueArms, activeDimensions, problemTypes)
}

function baseArmLabels(
  phase: PipelinePhase,
  sceneMarkers: MapSceneMarker[],
  cognition: CognitionPayload | null,
): ArmSceneLabel[] {
  const fromMarkers = buildArmLabelsFromScene(sceneMarkersForPhase(phase, sceneMarkers), null)
  // traffic：仅进口/排队标识，不补充分向饱和度（留到 direction 阶段一次性呈现）
  if (phase === 'traffic') {
    return stripSaturationFromLabels(fromMarkers)
  }
  if (phase !== 'direction' && phase !== 'saturation') return fromMarkers
  const covered = new Set(fromMarkers.map((l) => l.dir))
  const fromGroups = buildArmLabelsFromDirectionGroups(cognition).filter((l) => !covered.has(l.dir))
  for (const l of fromGroups) covered.add(l.dir)
  const fromLinks = buildArmLabelsFromEntranceLinks(cognition, covered)
  return [...fromMarkers, ...fromGroups, ...fromLinks]
}

/** 排队长度标签优先覆盖同进口的常规标签（仅排队维度相关的阶段）。 */
function mergeQueueLabels(
  phase: PipelinePhase,
  base: ArmSceneLabel[],
  queueArms: ChannelQueueArm[],
  activeDimensions?: string[],
  problemTypes: string[] = [],
): ArmSceneLabel[] {
  if (!QUEUE_LABEL_PHASES.includes(phase)) return base
  if (!isPresentationDimActive(activeDimensions, 'queue')) return base
  const primary = resolvePrimaryProblemType(problemTypes)
  const includeSaturation =
    SATURATION_ON_MAP_PHASES.includes(phase) && primary !== 'spillback'
  const queueLabels = buildArmLabelsFromQueue(queueArms, { includeSaturation })
  if (!queueLabels.length) return base
  const byDir = new Map(base.map((l) => [l.dir, l]))
  for (const q of queueLabels) {
    const existing = byDir.get(q.dir)
    const queueText = q.line2.replace(/^饱和[\d.]+ · /, '').trim()
    if (existing?.line2 && queueText) {
      const mergedLine2 = existing.line2.includes('排队')
        ? existing.line2
        : `${existing.line2} · ${queueText}`
      byDir.set(q.dir, { ...existing, line2: mergedLine2, colorHex: q.colorHex || existing.colorHex })
    } else {
      byDir.set(q.dir, q)
    }
  }
  return [...byDir.values()]
}

function applyDirectionRoleOnArms(
  layer: PhaseHighlightTarget,
  phase: PipelinePhase,
  highlightDirs: string[],
  protectedDirs: string[],
) {
  if (!ROLE_HIGHLIGHT_PHASES.includes(phase)) {
    layer.applyDirectionRoleHighlight([], [])
    return
  }
  const focusGroups = normalizeAxisFocusGroups(
    highlightDirs
      .map((d) => toAxisFocusGroup(d))
      .filter((g): g is NonNullable<ReturnType<typeof toAxisFocusGroup>> => Boolean(g)),
  )
  const focus = focusGroups.flatMap((group) => highlightDirsForGroup(group))
  const protect = protectedDirs.flatMap((group) => highlightDirsForGroup(group))
  layer.applyDirectionRoleHighlight(focus, protect)
}

/** 阶段→标注调度，复刻 ChannelizationCanvas3D.applyPhaseHighlight。 */
export function applyPhaseHighlight(layer: PhaseHighlightTarget, params: PhaseHighlightParams): void {
  layer.clearCheck()
  layer.applyArmSceneLabels([])
  const phase = params.phase ?? 'idle'
  const isStructure = COGNITION_STRUCTURE_PHASES.includes(phase)
  const allowRuntimeMetrics = params.allowRuntimeMetrics !== false

  if (params.highlightTurn && !isStructure && allowRuntimeMetrics) {
    layer.applyTurnHighlight({
      dir: params.highlightTurn.dir,
      turnCode: turnCodeFromLabel(params.highlightTurn.turn),
      label: params.highlightTurn.label ?? `${params.highlightTurn.dir}${params.highlightTurn.turn}`,
      saturation: params.highlightTurn.saturation ?? undefined,
    })
    return
  }

  const ev = buildHighlightEvidence(
    params.cognition,
    params.evidence ?? null,
    params.runtimeMetrics ?? null,
  )

  if (isStructure || !allowRuntimeMetrics) return

  if (phase === 'saturation') {
    const sat = ev.saturation_max ?? null
    if (sat == null) return
    layer.applyCheckHighlight('saturation', highlightVerdict(sat, 0.85, 0.65), ev)
  } else if (phase === 'traffic') {
    // 流量阶段不叠加饱和度浮标，避免与 saturation 阶段重复
  } else if (phase === 'imbalance') {
    const imb = ev.unbalance_index ?? null
    if (imb == null) return
    layer.applyCheckHighlight('imbalance', highlightVerdict(imb, 0.35, 0.25), ev)
  } else if (phase === 'granularity') {
    const sat = ev.max_turn_saturation ?? ev.saturation_max ?? null
    if (sat == null) return
    layer.applyCheckHighlight('saturation', highlightVerdict(sat, 0.85, 0.65), ev)
  }

  applyDirectionRoleOnArms(layer, phase, params.highlightDirs ?? [], params.protectedDirs ?? [])
  let labels = armLabelsForPhase(
    phase,
    params.sceneMarkers ?? [],
    params.cognition,
    params.queueArms ?? [],
    params.activeDimensions,
    params.problemTypes ?? [],
    params.highlightDirs ?? [],
    params.protectedDirs ?? [],
    params.runtimeMetrics?.imbalance_index ?? params.runtimeMetrics?.unbalance_index ?? null,
  )
  const usingRoleLabels = Boolean(params.highlightDirs?.length || params.protectedDirs?.length)
  if (!usingRoleLabels && SATURATION_ON_MAP_PHASES.includes(phase)) {
    labels = enrichSaturationHints(labels)
  } else if (!usingRoleLabels) {
    labels = stripSaturationFromLabels(labels)
  }
  layer.applyArmSceneLabels(labels)

  const hasQueueText = labels.some((l) => l.line2?.includes('排队'))
  if (
    hasQueueText &&
    QUEUE_LABEL_PHASES.includes(phase) &&
    isPresentationDimActive(params.activeDimensions, 'queue')
  ) {
    const activeQueues = (params.queueArms ?? []).filter((q) => q.queueM > 0)
    if (activeQueues.length) layer.applyQueueLengthHighlight(activeQueues)
  }
}
