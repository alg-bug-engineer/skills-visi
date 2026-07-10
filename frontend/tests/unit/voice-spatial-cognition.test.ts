import { describe, expect, it } from 'vitest'
import { voiceSpatialCognition } from '@/services/voiceSpatialCognition'
import { voiceTextForAct } from '@/services/voiceStepSync'
import { ACT_DEFS } from '@/composables/useTimeline'
import type { RunResponse } from '@/api/types'

describe('voiceSpatialCognition', () => {
  it('reads axis_roads from spatial_scene without fabricating', () => {
    const resp: RunResponse = {
      trace_id: 't',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: {
        intent: {
          spatial_scene: {
            target: { inter_name: '坤顺路与奥体西路路口' },
            axis_roads: { ew_road: '坤顺路', ns_road: '奥体西路', available: true },
          },
        },
      } as RunResponse['phases'],
      plan: null,
      phase_results: [],
    }
    expect(voiceSpatialCognition(resp)).toBe('坤顺路与奥体西路路口，东西向是坤顺路，南北向是奥体西路')
  })

  it('degrades when one axis road is missing', () => {
    const resp: RunResponse = {
      trace_id: 't',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: {
        intent: {
          spatial_scene: {
            target: { inter_name: '测试路口' },
            axis_roads: { ew_road: '经十路', ns_road: null },
          },
        },
      } as RunResponse['phases'],
      plan: null,
      phase_results: [],
    }
    expect(voiceSpatialCognition(resp)).toBe('测试路口，东西向是经十路，南北向道路信息待补全')
  })

  it('returns null when no axis data', () => {
    expect(voiceSpatialCognition(null)).toBeNull()
  })

  it('prefixes act2_locate voice with spatial cognition', () => {
    const act = ACT_DEFS.find((a) => a.id === 'act2_locate')!
    const resp: RunResponse = {
      trace_id: 't',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: { intersection_name: '经十路与转山西路路口' } as RunResponse['diagnosis_ticket'],
      phases: {
        intent: {
          spatial_scene: {
            target: { inter_name: '经十路与转山西路路口' },
            axis_roads: { ew_road: '经十路', ns_road: '转山西路' },
          },
        },
      } as RunResponse['phases'],
      plan: null,
      phase_results: [],
    }
    const text = voiceTextForAct(act, resp)
    expect(text).toContain('东西向是经十路')
    expect(text).toContain('南北向是转山西路')
  })
})
