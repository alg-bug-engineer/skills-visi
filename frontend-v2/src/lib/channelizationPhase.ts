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
import { COGNITION_STRUCTURE_PHASES } from '../types/presentation'
import {
  buildHighlightEvidence,
  highlightVerdict,
  turnCodeFromLabel,
} from '../utils/cognitionChannelAdapter'
import {
  buildArmLabelsFromScene,
  buildArmLabelsFromDirectionGroups,
  buildArmLabelsFromEntranceLinks,
} from '../utils/channelArmLabels'
import { highlightDirsForGroup } from '../utils/evidencePresentation'
import type { ArmSceneLabel, HighlightEvidence, TurnHighlightSpec } from './channelizationAmap'

export interface PhaseHighlightTarget {
  clearCheck(): void
  applyTurnHighlight(spec: TurnHighlightSpec): void
  applyCheckHighlight(indicatorId: string, verdict: string, evidence: HighlightEvidence): void
  applyDirectionRoleHighlight(focusDirs: string[], protectDirs: string[]): void
  applyArmSceneLabels(labels: ArmSceneLabel[]): void
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
}

const ARM_LABEL_PHASES: PipelinePhase[] = [
  'direction',
  'traffic',
  'saturation',
  'granularity',
  'timing',
  'imbalance',
]

function sceneMarkersForPhase(phase: PipelinePhase, markers: MapSceneMarker[]): MapSceneMarker[] {
  if (phase === 'direction') return markers
  return markers.filter((m) => m.variant !== 'protected' && !(m.title?.includes('保护')))
}

function armLabelsForPhase(
  phase: PipelinePhase,
  sceneMarkers: MapSceneMarker[],
  cognition: CognitionPayload | null,
): ArmSceneLabel[] {
  if (!ARM_LABEL_PHASES.includes(phase)) return []
  const fromMarkers = buildArmLabelsFromScene(sceneMarkersForPhase(phase, sceneMarkers), null)
  if (phase !== 'direction' && phase !== 'traffic') return fromMarkers
  const covered = new Set(fromMarkers.map((l) => l.dir))
  const fromGroups = buildArmLabelsFromDirectionGroups(cognition).filter((l) => !covered.has(l.dir))
  for (const l of fromGroups) covered.add(l.dir)
  const fromLinks = buildArmLabelsFromEntranceLinks(cognition, covered)
  return [...fromMarkers, ...fromGroups, ...fromLinks]
}

function applyDirectionRoleOnArms(
  layer: PhaseHighlightTarget,
  phase: PipelinePhase,
  highlightDirs: string[],
  protectedDirs: string[],
) {
  if (phase !== 'direction') {
    layer.applyDirectionRoleHighlight([], [])
    return
  }
  const focus = highlightDirs
  const protect = protectedDirs.flatMap((group) => highlightDirsForGroup(group))
  layer.applyDirectionRoleHighlight(focus, protect)
}

/** 阶段→标注调度，复刻 ChannelizationCanvas3D.applyPhaseHighlight。 */
export function applyPhaseHighlight(layer: PhaseHighlightTarget, params: PhaseHighlightParams): void {
  layer.clearCheck()
  const phase = params.phase ?? 'idle'
  const isStructure = COGNITION_STRUCTURE_PHASES.includes(phase)

  if (params.highlightTurn && !isStructure) {
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

  if (isStructure) return

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
  layer.applyArmSceneLabels(armLabelsForPhase(phase, params.sceneMarkers ?? [], params.cognition))
}
