import { describe, expect, it } from 'vitest'
import {
  armAngleFromLink,
  calcBoxR,
  gatherArms,
  laneColor,
  laneLabel,
  parseLaneInfo,
  type ChannelLink,
} from '@/map/channelizationGeometry'
import { buildDownstreamTopology } from '@/map/downstreamTopologyLayer'

describe('channelization geometry helpers', () => {
  it('parses lane_info and falls back to straight lanes by lane count', () => {
    expect(parseLaneInfo({ lane_info: 'B|C|D' })).toEqual(['B', 'C', 'D'])
    expect(parseLaneInfo({ c_lane_num: 3 })).toEqual(['C', 'C', 'C'])
  })

  it('maps lane function to reference colors and labels', () => {
    expect(laneColor('B')).toBe('#2189ff')
    expect(laneColor('C')).toBe('#39dfff')
    expect(laneColor('D')).toBe('#2ed573')
    expect(laneColor('CD')).toBe('#ffd247')
    expect(laneLabel('AB')).toBe('掉头左转')
  })

  it('uses real path to compute outward arm angle', () => {
    const link: ChannelLink = {
      link_role: 'entrance',
      path: [
        [117.1, 36.65],
        [117.11, 36.65],
      ],
    }
    expect(armAngleFromLink(link)).toBeCloseTo(270, 0)
  })

  it('groups entrance and exit links into arms and computes bounded box radius', () => {
    const links: ChannelLink[] = [
      { link_role: 'entrance', lane_info: 'B|C|D', path: [[117.1, 36.65], [117.11, 36.65]] },
      { link_role: 'exit', lane_num: 2, path: [[117.11, 36.6502], [117.1, 36.6502]] },
    ]
    const arms = gatherArms(links)
    expect(arms).toHaveLength(1)
    expect(arms[0].inLink?.lane_info).toBe('B|C|D')
    expect(arms[0].outLink?.lane_num).toBe(2)
    expect(calcBoxR(arms)).toBeGreaterThanOrEqual(18)
  })
})

describe('downstream topology extraction', () => {
  it('keeps all real exit-link downstream nodes and highlights traced turn nodes', () => {
    const scene = {
      channelization_map: {
        links: [
          {
            link_id: 'east',
            link_role: 'exit',
            adjacent_inter_id: 'D1',
            adjacent_inter_name: '经十路与奥体中路路口',
            adjacent_lng: 117.12,
            adjacent_lat: 36.65,
            path: [[117.11, 36.65], [117.12, 36.65]],
          },
          {
            link_id: 'north',
            link_role: 'exit',
            adjacent_inter_id: 'D2',
            adjacent_inter_name: '解放东路与奥体西路路口',
            adjacent_lng: 117.11,
            adjacent_lat: 36.66,
            path: [[117.11, 36.65], [117.11, 36.66]],
          },
        ],
      },
      downstream_trace_map: {
        turn_traces: [{ downstream_inter_id: 'D1' }],
        adjacent_intersections: [
          {
            inter_id: 'D1',
            metrics: {
              queue_storage_ratio_max: 0.72,
              saturation_rate: 0.88,
              green_utilization: null,
            },
            remaining_storage_m: 80,
          },
        ],
      },
    }

    const topology = buildDownstreamTopology(scene, [117.11, 36.65])

    expect(topology.target).toEqual([117.11, 36.65])
    expect(topology.nodes).toHaveLength(2)
    expect(topology.nodes.find((n) => n.id === 'D1')?.highlighted).toBe(true)
    expect(topology.nodes.find((n) => n.id === 'D1')?.metrics?.queueRatio).toBe(0.72)
    expect(topology.nodes.find((n) => n.id === 'D1')?.metrics?.saturation).toBe(0.88)
    expect(topology.nodes.find((n) => n.id === 'D1')?.metrics?.greenUtilization).toBeUndefined()
    expect(topology.nodes.find((n) => n.id === 'D1')?.metrics?.remainingStorageM).toBe(80)
    expect(topology.nodes.find((n) => n.id === 'D2')?.highlighted).toBe(false)
    expect(topology.edges.every((e) => e.path.length >= 2)).toBe(true)
  })
})
