import { describe, expect, it } from 'vitest'
import type { ActMapScene, ActDef } from '@/composables/useTimeline'
import { ACT_DEFS, narrationFor, summaryFor } from '@/composables/useTimeline'
import { sceneEvidencePolicy } from '@/map/sceneEvidencePolicy'
import type { RunResponse } from '@/api/types'

const diagnosticResponse = {
  diagnosis_ticket: {
    intersection_name: '文化西路与舜华路交叉口',
    direction: '东',
    movement: '直行',
    problem_type: 'queue_overflow',
    object_type: 'intersection',
    inter_id: 'T',
    lng: 117.11,
    lat: 36.65,
    time_range: '18:10-18:30',
    period: 'evening_peak',
    constraints: ['优先避免下游继续外溢'],
    diagnosis_scope: '目标路口与上下游',
    governance_goal: '控制外溢扩散',
    match_confidence: 0.96,
    match_method: 'registry',
  },
  phases: {
    intent: {
      spatial_scene: {
        available: true,
        recognition_steps: [],
        target: null,
        highlight_path: [],
        upstream_nodes: [],
        downstream_nodes: [],
      },
    },
    diagnosis: {
      metrics: {
        queue_length_m: 120,
        storage_length_m: 150,
        queue_ratio: 0.8,
        saturation: 0.86,
        green_utilization: 0.72,
        stop_count: 3,
        avg_delay_s: 58,
        time_series_trend: 'rising',
      },
      overflow_verification: {
        verified: true,
        risk_level: 'high',
        message: '东向西直行排队接近进口道空间边界',
      },
      downstream_diagnosis: {
        scenario: 'downstream_blocked',
        release_answer: '不宜直接扩大目标方向放行，应先确认下游剩余接纳空间。',
        narrative: '当前表现不是简单加绿问题，而是下游接不住。',
        can_simple_add_green: false,
      },
    },
  },
  plan: null,
  phase_results: [],
} as unknown as RunResponse

function act(id: string): ActDef {
  const found = ACT_DEFS.find((a) => a.id === id)
  if (!found) throw new Error(`missing act ${id}`)
  return found
}

describe('presentation closure semantics', () => {
  it('gates map evidence so recognition does not show validation markers or downstream topology', () => {
    const recognition = sceneEvidencePolicy(act('act2_locate').scene, { showMetrics: true })
    expect(recognition.metricMarkers).toBe(false)
    expect(recognition.downstreamTopology).toBe(false)
    expect(recognition.channelization).toBe(false)

    const validation = sceneEvidencePolicy(act('act3_overflow').scene, { showMetrics: true })
    expect(validation.metricMarkers).toBe(true)
    expect(validation.channelization).toBe(true)
    expect(validation.downstreamTopology).toBe(false)

    const downstream = sceneEvidencePolicy(act('act5_bottleneck').scene, { showMetrics: true })
    expect(downstream.metricMarkers).toBe(false)
    expect(downstream.channelization).toBe(true)
    expect(downstream.downstreamTopology).toBe(true)

    const topology = sceneEvidencePolicy(act('act6_corridor').scene, { showMetrics: true })
    expect(topology.downstreamTopology).toBe(false)
    expect(topology.trace).toBe(true)
    expect(topology.metricMarkers).toBe(false)

    const cause = sceneEvidencePolicy(act('act4_attribution').scene, { showMetrics: true })
    expect(cause.trace).toBe(false)
    expect(cause.causeAnnotation).toBe(true)
    expect(cause.downstreamTopology).toBe(false)

    const cases = sceneEvidencePolicy(act('act7_cases').scene, { showMetrics: true })
    expect(cases.causeAnnotation).toBe(true)
    expect(cases.downstreamTopology).toBe(false)

    const strategy = sceneEvidencePolicy(act('act8_strategy').scene, { showMetrics: true })
    expect(strategy.controlScope).toBe(true)
    expect(strategy.downstreamTopology).toBe(false)

    const plan = sceneEvidencePolicy(act('act9_plan').scene, { showMetrics: true })
    expect(plan.planPreview).toBe(true)
    expect(plan.diagnosisCompare).toBe(false)
  })

  it('keeps frontend process copy in production terminology', () => {
    const scenes: ActMapScene[] = ACT_DEFS.map((a) => a.scene)
    expect(scenes.length).toBeGreaterThan(0)

    const copy = ACT_DEFS.flatMap((a) => [
      a.pipelineNode,
      a.processTitle,
      ...narrationFor(a, diagnosticResponse),
      summaryFor(a, diagnosticResponse),
    ]).join('\n')

    expect(copy).not.toMatch(/幕/)
    expect(copy).not.toMatch(/\bvs\b/i)
    expect(copy).not.toContain('下游接不住')
    expect(copy).not.toContain('智能体')
  })
})
