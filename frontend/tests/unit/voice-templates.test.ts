import { describe, expect, it } from 'vitest'
import { ACT_DEFS, summaryFor } from '@/composables/useTimeline'
import { composeVoiceAnnounce, renderVoiceTemplate, VOICE_TEMPLATES, voiceMethodFor } from '@/config/voiceTemplates'
import { voiceSlotsForAct } from '@/services/voiceSlotFillers'
import { voiceTextForAct } from '@/services/voiceStepSync'
import { voiceSpatialCognition } from '@/services/voiceSpatialCognition'
import {
  resetAbsorptionVoiceKeys,
  voiceCueForAbsorptionStage,
  voiceCueForAbsorptionStart,
} from '@/services/voiceAbsorptionSync'
import { ABSORPTION_STAGE_VOICE, ABSORPTION_VOICE_GUIDE } from '@/config/voiceTemplates'
import { downstreamConclusion } from '@/utils/downstream'
import fixture from '@/mock/run_1_fixture.json'
import type { RunResponse } from '@/api/types'

const fx = fixture as unknown as RunResponse

describe('voice templates', () => {
  it('renders slot placeholders', () => {
    expect(renderVoiceTemplate('排队比{queueRatio}，饱和度{saturation}', { queueRatio: '1.2', saturation: '85%' })).toBe(
      '排队比1.2，饱和度85%',
    )
  })

  it('composes purpose + method without conclusion slot', () => {
    const act = ACT_DEFS[2]
    const def = VOICE_TEMPLATES[act.id]
    const slots = voiceSlotsForAct(act)
    const text = composeVoiceAnnounce(def, slots)
    expect(text).toContain('溢出证据核验')
    expect(text).not.toContain('核心结论')
    expect(text).toContain('排队比')
  })

  it('voiceTextForAct omits conclusion before diagnosis act', () => {
    const text = voiceTextForAct(ACT_DEFS[0], fx)
    expect(text).not.toContain('核心结论')
    expect(text).toContain('诊断对象识别')
    const name = fx.diagnosis_ticket?.intersection_name
    if (name) expect(text).not.toContain(name)
    expect(text).not.toMatch(/溢出风险|排队尚在/)
  })

  it('voiceTextForAct includes diagnosis conclusion from act3 onward', () => {
    const text = voiceTextForAct(ACT_DEFS[2], fx)
    expect(text).not.toContain('核心结论')
    expect(text).toContain('溢出证据核验')
    expect(text).toContain(fx.phases?.diagnosis?.overflow_verification?.message ?? '')
  })

  it('healthy overflow act includes healthy conclusion in voice', () => {
    const healthyFx: RunResponse = {
      ...fx,
      phases: {
        ...fx.phases,
        diagnosis: { ...(fx.phases?.diagnosis ?? {}), healthy: true },
      },
    }
    const text = voiceTextForAct(ACT_DEFS[2], healthyFx)
    expect(text).not.toContain('核心结论')
    expect(text).toContain('无溢出风险')
    expect(text).toContain('溢出证据核验')
  })

  it('bottleneck act voice reads downstream conclusion only', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_bottleneck')!
    const text = voiceTextForAct(act, fx)
    const conclusion = downstreamConclusion(fx.phases?.diagnosis?.downstream_diagnosis)
    const method = voiceMethodFor(act.id)

    expect(text).toContain('下游承接能力判别')
    expect(text).toContain(conclusion)
    expect(text).not.toContain('评估相邻下游信控节点')
    if (method) expect(text).not.toContain(method)
  })

  it('cause act voice reads primary cause only', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act6_cause')!
    const text = voiceTextForAct(act, fx)
    const primary = fx.phases?.cause?.cause_analysis?.primary_cause ?? ''
    const narrative = fx.phases?.cause?.cause_analysis?.narrative ?? ''
    const shortPrimary = primary.split(/[（(]/)[0]?.trim() ?? primary

    expect(text).toContain(shortPrimary)
    expect(text).not.toContain(primary.slice(shortPrimary.length))
    if (narrative) expect(text).not.toContain(narrative)
  })

  it('strategy and plan acts omit voice conclusion', () => {
    for (const id of ['act7_strategy', 'act8_plan'] as const) {
      const act = ACT_DEFS.find((item) => item.id === id)!
      const text = voiceTextForAct(act, fx)
      const summary = summaryFor(act, fx)

      expect(text).not.toContain('核心结论')
      expect(text).not.toContain(summary)
    }
  })

  it('feedback act voice reads title only', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act9_feedback')!
    const text = voiceTextForAct(act, fx)

    expect(text).toBe('方案确认与经验沉淀。')
    expect(text).not.toContain('等待方案确认')
    expect(text).not.toContain('记录决策')
  })
})

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

describe('voiceAbsorptionSync', () => {
  it('播报经验吸收开始与阶段文案', () => {
    resetAbsorptionVoiceKeys()
    const start = voiceCueForAbsorptionStart('run-1')
    expect(start?.text).toBe(ABSORPTION_VOICE_GUIDE.absorptionStart)
    expect(voiceCueForAbsorptionStart('run-1')).toBeNull()

    const recap = voiceCueForAbsorptionStage('run-1', 'recap')
    expect(recap?.text).toBe(ABSORPTION_STAGE_VOICE.recap)
    expect(voiceCueForAbsorptionStage('run-1', 'decompose')).toBeNull()
  })
})
