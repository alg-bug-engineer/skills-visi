import type { ActMapScene } from '@/composables/useTimeline'

export type EvidenceStage =
  | 'overview'
  | 'recognition'
  | 'overflow_validation'
  | 'downstream_topology'
  | 'flow_trace'
  | 'cause_annotation'
  | 'control_scope'
  | 'plan_output'
  | 'feedback'

export interface SceneEvidencePolicy {
  metricMarkers: boolean
  channelization: boolean
  downstreamTopology: boolean
  trace: boolean
  controlScope: boolean
  diagnosisCompare: boolean
  causeAnnotation: boolean
  planPreview: boolean
}

export function sceneEvidencePolicy(
  scene: ActMapScene,
  opts: { showMetrics?: boolean } = {},
): SceneEvidencePolicy {
  const stage = scene.evidence ?? scene.kind
  return {
    metricMarkers: Boolean(opts.showMetrics && stage === 'overflow_validation'),
    channelization:
      stage === 'overflow_validation' ||
      stage === 'downstream_topology' ||
      stage === 'plan_output' ||
      stage === 'cause_annotation',
    downstreamTopology:
      stage === 'downstream_topology' ||
      stage === 'flow_trace' ||
      stage === 'control_scope' ||
      stage === 'cause_annotation' ||
      stage === 'feedback',
    trace: stage === 'flow_trace' || stage === 'feedback',
    controlScope: stage === 'control_scope',
    diagnosisCompare: stage === 'overflow_validation' || stage === 'downstream_topology',
    causeAnnotation: stage === 'cause_annotation',
    planPreview: stage === 'plan_output',
  }
}
