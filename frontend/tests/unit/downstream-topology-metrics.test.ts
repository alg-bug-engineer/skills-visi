import { describe, expect, it } from 'vitest'
import {
  buildDownstreamTopology,
  formatMovementSummary,
  formatNodeMetrics,
  resolvePrimaryDownstreamFocus,
  topologyLabelOffsetClass,
} from '@/map/downstreamTopologyLayer'

describe('downstream topology metric labels', () => {
  it('hides zero saturation and only shows meaningful metrics', () => {
    const scene = {
      channelization_map: {
        links: [
          {
            link_id: 'east',
            link_role: 'exit',
            adjacent_inter_id: 'D1',
            adjacent_inter_name: '奥体西路与解放东路路口',
            adjacent_lng: 117.11,
            adjacent_lat: 36.66,
            path: [
              [117.1, 36.65],
              [117.11, 36.66],
            ],
            metrics: { saturation: 0, green_utilization: null },
          },
        ],
      },
      downstream_trace_map: {
        turn_traces: [],
        adjacent_intersections: [
          {
            inter_id: 'D1',
            metrics: {
              saturation_rate: 0,
              green_utilization: 0.4137,
            },
          },
        ],
      },
    }

    const topology = buildDownstreamTopology(scene, [117.1, 36.65])
    const label = formatNodeMetrics(topology.nodes[0]?.metrics)
    expect(label).not.toContain('饱和')
    expect(label).toContain('绿灯 0.41')
    expect(label).not.toContain('%')
    expect(label).not.toBe('指标暂无')
  })

  it('presents left-through-right relations and marks the selected movement', () => {
    const scene = {
      channelization_map: {
        links: [
          {
            link_id: 'east',
            link_role: 'exit',
            adjacent_inter_id: 'D1',
            adjacent_inter_name: '东侧下游',
            adjacent_lng: 117.11,
            adjacent_lat: 36.66,
            path: [
              [117.1, 36.65],
              [117.11, 36.66],
            ],
          },
        ],
      },
      downstream_trace_map: {
        turn_traces: [
          { downstream_inter_id: 'D1', turn_label: '左转', share_pct: 21, selected: false },
          { downstream_inter_id: 'D1', turn_label: '直行', share_pct: 63, selected: true },
          { downstream_inter_id: 'D1', turn_label: '右转', share_pct: 16, selected: false },
        ],
      },
    }

    const topology = buildDownstreamTopology(scene, [117.1, 36.65])
    const summary = formatMovementSummary(topology.nodes[0]?.movements)
    expect(summary).toContain('左转 21%')
    expect(summary).toContain('直行 63%（目标）')
    expect(summary).toContain('右转 16%')
  })

  it('offsets topology cards away from the target along the dominant axis', () => {
    const target: [number, number] = [117.1, 36.65]
    expect(topologyLabelOffsetClass(target, [117.12, 36.65])).toBe('is-offset-e')
    expect(topologyLabelOffsetClass(target, [117.08, 36.65])).toBe('is-offset-w')
    expect(topologyLabelOffsetClass(target, [117.1, 36.67])).toBe('is-offset-n')
    expect(topologyLabelOffsetClass(target, [117.1, 36.63])).toBe('is-offset-s')
  })

  it('resolves and marks the primary downstream focus for capacity framing', () => {
    const resp = {
      phases: {
        diagnosis: {
          downstream_diagnosis: {
            primary_downstream: {
              inter_id: 'D1',
              inter_name: '永绥路与齐音路路口',
            },
          },
          map_scenes: {
            diagnosis_compare: {
              downstream: {
                inter_id: 'D1',
                inter_name: '永绥路与齐音路路口',
                lng: 117.108427,
                lat: 36.661851,
              },
            },
            channelization_map: {
              links: [
                {
                  link_id: 'east',
                  link_role: 'exit',
                  adjacent_inter_id: 'D1',
                  adjacent_inter_name: '永绥路与齐音路路口',
                  adjacent_lng: 117.108427,
                  adjacent_lat: 36.661851,
                  path: [
                    [117.1084, 36.6629],
                    [117.108427, 36.661851],
                  ],
                },
              ],
            },
            downstream_trace_map: { turn_traces: [], adjacent_intersections: [] },
          },
        },
      },
    }

    const focus = resolvePrimaryDownstreamFocus(resp)
    expect(focus?.id).toBe('D1')
    expect(focus?.position).toEqual([117.108427, 36.661851])

    const topology = buildDownstreamTopology(resp.phases.diagnosis.map_scenes, [117.1084, 36.6629], {
      primaryId: focus?.id,
      primaryFocus: focus,
    })
    const primary = topology.nodes.find((n) => n.id === 'D1')
    expect(primary?.primary).toBe(true)
    expect(primary?.highlighted).toBe(true)
  })
})
