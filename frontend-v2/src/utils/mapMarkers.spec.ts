import { describe, expect, it } from 'vitest'
import type { CognitionPayload } from '../types/map'
import { mergeSceneMarkers } from './mapMarkers'

const COG: CognitionPayload = {
  intersection: { inter_id: 'x', name: '测试路口', lon: 117.1, lat: 36.6 },
  arms: [],
  links: [
    {
      link_id: 'w',
      dir4_label: '西',
      link_role: 'entrance',
      path: [
        [117.099, 36.6],
        [117.1, 36.6],
      ],
      lane_num: 3,
    },
  ],
  metrics_by_turn: [{ label: '西直行', dir4_label: '西', turn_dir_no: 2, turn_saturation: 0.03 }],
}

describe('mergeSceneMarkers runtime gate', () => {
  it('builds turn markers for traffic phase when runtime metrics allowed', () => {
    const markers = mergeSceneMarkers(
      { action: 'map_scene', phase: 'traffic' },
      COG,
      { allowRuntimeMetrics: true },
    )
    expect(markers.some((m) => m.title === '西直行')).toBe(true)
  })

  it('skips turn markers before runtime step is revealed', () => {
    const markers = mergeSceneMarkers(
      { action: 'map_scene', phase: 'traffic' },
      COG,
      { allowRuntimeMetrics: false },
    )
    expect(markers).toEqual([])
  })

  it('filters metric markers from backend payload when gated', () => {
    const markers = mergeSceneMarkers(
      {
        action: 'map_scene',
        phase: 'traffic',
        markers: [
          {
            id: 't1',
            lon: 117.1,
            lat: 36.6,
            kind: 'metric',
            variant: 'turn',
            title: '西直行',
            value: '0.03',
          },
        ],
      },
      COG,
      { allowRuntimeMetrics: false },
    )
    expect(markers).toEqual([])
  })

  it('drops evidence and suggestion map cards from backend payload', () => {
    const markers = mergeSceneMarkers(
      {
        action: 'map_scene',
        phase: 'rule',
        markers: [
          {
            id: 'ev1',
            lon: 117.1,
            lat: 36.6,
            kind: 'evidence',
            title: '证据',
            value: '0.53',
          },
          {
            id: 'sg1',
            lon: 117.1,
            lat: 36.6,
            kind: 'suggestion',
            title: '建议',
            value: '+0s',
          },
          {
            id: 'mt1',
            lon: 117.1,
            lat: 36.6,
            kind: 'metric',
            title: '西进口',
            value: '1.94',
          },
        ],
      },
      COG,
      { allowRuntimeMetrics: true },
    )

    expect(markers.map((m) => m.id)).toEqual(['mt1'])
  })
})
