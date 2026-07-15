import { describe, expect, it } from 'vitest'
import { ACT_DEFS, summaryFor } from '@/composables/useTimeline'
import { composeVoiceAnnounce, renderVoiceTemplate, VOICE_TEMPLATES, voiceMethodFor } from '@/config/voiceTemplates'
import { voiceSlotsForAct } from '@/services/voiceSlotFillers'
import { buildVoiceCue, voiceTextForAct } from '@/services/voiceStepSync'
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
    expect(text).toContain('证据核验')
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
    expect(text).toContain('证据核验')
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
    expect(text).toContain('证据核验')
  })

  it('bottleneck act voice reads downstream conclusion only', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act5_bottleneck')!
    const text = voiceTextForAct(act, fx)
    const conclusion = downstreamConclusion(fx.phases?.diagnosis?.downstream_diagnosis)
    const method = voiceMethodFor(act.id)

    expect(text).toContain('下游承接能力判别')
    expect(text).toContain(conclusion)
    expect(text).not.toContain('评估相邻下游信控节点')
    if (method) expect(text).not.toContain(method)
  })

  it('attribution act voice reads primary cause only', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const text = voiceTextForAct(act, fx)
    const primary = fx.phases?.cause?.cause_analysis?.primary_cause ?? ''
    const narrative = fx.phases?.cause?.cause_analysis?.narrative ?? ''
    const shortPrimary = primary.split(/[（(]/)[0]?.trim() ?? primary

    expect(text).toContain(shortPrimary)
    expect(text).not.toContain(primary.slice(shortPrimary.length))
    if (narrative) expect(text).not.toContain(narrative)
  })

  it('strategy and plan acts omit voice conclusion', () => {
    for (const id of ['act8_strategy', 'act9_plan'] as const) {
      const act = ACT_DEFS.find((item) => item.id === id)!
      const text = voiceTextForAct(act, fx)
      const summary = summaryFor(act, fx)

      expect(text).not.toContain('核心结论')
      expect(text).not.toContain(summary)
    }
  })

  it('feedback act has no voice cue', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act10_feedback')!
    expect(buildVoiceCue(act, 'run-1', fx)).toBeNull()
    expect(VOICE_TEMPLATES[act.id]).toBeUndefined()
  })

  it('voice step titles stay aligned with process titles for all speakable acts', () => {
    for (const act of ACT_DEFS) {
      if (act.id === 'act10_feedback') continue
      const def = VOICE_TEMPLATES[act.id]
      expect(def, `missing voice template for ${act.id}`).toBeTruthy()
      expect(def!.stepTitle).toBe(act.processTitle)
      const text = voiceTextForAct(act, fx)
      expect(text).toContain(act.processTitle)
    }
  })

  it('cases act voice reports match counts without primary-cause narration', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act7_cases')!
    const text = voiceTextForAct(act, fx)
    const primary = fx.phases?.cause?.cause_analysis?.primary_cause ?? ''
    const matched = fx.phases?.cause?.case_cards?.matched_count
    const high = fx.phases?.cause?.case_cards?.high_similarity_count ?? 0

    expect(text).toContain('案例校验')
    if (matched != null) expect(text).toContain(`匹配同类案例 ${matched} 个`)
    expect(text).toContain(`高度相似 ${high} 个`)
    if (primary) expect(text).not.toContain(primary.split(/[（(]/)[0]?.trim() ?? primary)
  })

  it('attribution voice purpose reflects post-evidence order', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const text = voiceTextForAct(act, fx)
    expect(text).toContain('归因分析')
    expect(text).toContain('证据核验之后')
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
