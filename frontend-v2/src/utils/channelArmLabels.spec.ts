import { describe, expect, it } from 'vitest'
import { buildArmLabelsFromScene } from './channelArmLabels'
import type { CognitionPayload, MapSceneMarker } from '../types/map'

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

  it('falls back to metrics_by_arm', () => {
    const cognition = {
      intersection: { inter_id: '1', name: '测试', lon: 117, lat: 36 },
      arms: [],
      metrics_by_arm: [{ link_id: 'l1', dir4_label: '南', saturation: 0.92 }],
    } as CognitionPayload
    const labels = buildArmLabelsFromScene([], cognition)
    expect(labels[0].dir).toBe('南')
    expect(labels[0].line2).toContain('0.92')
  })
})
