import { describe, expect, it } from 'vitest'
import {
  buildArmLabelsFromScene,
  buildArmLabelsFromDirectionGroups,
  buildArmLabelsFromEntranceLinks,
  buildArmLabelsFromQueue,
  buildRoleArmLabels,
  saturationProblemHint,
} from './channelArmLabels'
import type { ChannelQueueArm } from './cognitionChannelAdapter'
import type { CognitionPayload, MapSceneMarker } from '../types/map'

describe('saturationProblemHint', () => {
  it('maps saturation tiers to problem copy', () => {
    expect(saturationProblemHint(1.33)).toBe('过饱和 1.33')
    expect(saturationProblemHint(0.9)).toBe('饱和偏高 0.90')
    expect(saturationProblemHint(0.5)).toBe('饱和 0.50')
  })
})

describe('buildArmLabelsFromQueue', () => {
  it('renders queue length (m) + saturation for arms with queue', () => {
    const arms: ChannelQueueArm[] = [
      { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东进口', label: '东进口' },
      { armAngle: 90, queueM: 0, satPct: 30, satRatio: 0.3, dir4: '南进口', label: '南进口' },
    ]
    const labels = buildArmLabelsFromQueue(arms)
    // 仅排队>0 的进口出标签
    expect(labels).toHaveLength(1)
    expect(labels[0].dir).toBe('东')
    expect(labels[0].line2).toContain('排队~85m')
    expect(labels[0].line2).toContain('饱和0.95')
  })

  it('returns empty when no queue', () => {
    expect(buildArmLabelsFromQueue([])).toEqual([])
  })
})

describe('buildRoleArmLabels', () => {
  it('merges saturation imbalance and queue in one line for focus arm', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      metrics_by_arm: [{ link_id: 'w1', dir4_label: '西', saturation: 1.94 }],
    } as CognitionPayload
    const queueArms: ChannelQueueArm[] = [
      { armAngle: 270, queueM: 120, satPct: 194, satRatio: 1.94, dir4: '西', label: '西进口' },
    ]
    const labels = buildRoleArmLabels(['西'], [], cognition, queueArms, 0.38)
    const west = labels.find((l) => l.dir === '西')
    expect(west?.line2).toContain('饱和 1.94')
    expect(west?.line2).toContain('失衡 0.38')
    expect(west?.line2).toContain('排队~120m')
    expect(west?.line2?.split('饱和').length).toBe(2)
  })

  it('keeps protected arm saturation without imbalance', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      metrics_by_arm: [
        { link_id: 'w1', dir4_label: '西', saturation: 1.94 },
        { link_id: 'n1', dir4_label: '北', saturation: 0.42 },
      ],
    } as CognitionPayload
    const labels = buildRoleArmLabels(['西'], ['南北向'], cognition)
    expect(labels.find((l) => l.dir === '西')?.line1).toBe('关注 东西向')
    expect(labels.find((l) => l.dir === '北')?.line1).toBe('保护 南北向')
    expect(labels.find((l) => l.dir === '西')?.line2).toContain('饱和 1.94')
  })
})

describe('buildArmLabelsFromScene', () => {
  it('maps metric markers to arm dirs', () => {
    const markers: MapSceneMarker[] = [
      {
        id: 'm1',
        lon: 117,
        lat: 36,
        kind: 'metric',
        dir: '东',
        title: '东进口',
        value: '129%',
        severity: 'high',
      },
    ]
    const labels = buildArmLabelsFromScene(markers, null)
    expect(labels).toHaveLength(1)
    expect(labels[0].dir).toBe('东')
    expect(labels[0].line2).toContain('129')
  })

  it('fills metrics_by_arm when explicitly enabled', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      metrics_by_arm: [{ link_id: 'l1', dir4_label: '南', saturation: 0.92 }],
    } as CognitionPayload
    const labels = buildArmLabelsFromScene([], cognition, { fillFromCognition: true })
    expect(labels[0].dir).toBe('南')
    expect(labels[0].line2).toContain('0.92')
  })

  it('does not backfill from cognition by default', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      metrics_by_arm: [{ link_id: 'l1', dir4_label: '南', saturation: 0.92 }],
    } as CognitionPayload
    expect(buildArmLabelsFromScene([], cognition)).toHaveLength(0)
  })

  it('builds all direction groups for channelization labels', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      direction_groups: [
        { group: '东西向', saturation_max: 1.5, arm_labels: ['东', '西'] },
        { group: '南北向', saturation_max: 1.2, arm_labels: ['南', '北'] },
      ],
    } as CognitionPayload
    const labels = buildArmLabelsFromDirectionGroups(cognition)
    expect(labels.map((l) => l.dir).sort()).toEqual(['东', '北', '南', '西'])
    expect(labels.find((l) => l.dir === '南')?.line2).toBe('1.20')
  })

  it('does not emit placeholder labels for entrances without data', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      links: [
        { link_id: 'e1', link_role: 'entrance', dir4_label: '东进口', path: [[117.1, 36.6]] },
        { link_id: 's1', link_role: 'entrance', dir4_label: '南进口', path: [[117.05, 36.59]] },
      ],
    } as CognitionPayload
    expect(buildArmLabelsFromEntranceLinks(cognition, new Set(['东']))).toEqual([])
  })
})
