import { describe, expect, it } from 'vitest'
import { ACT_DEFS } from '@/composables/useTimeline'
import { composeVoiceAnnounce, renderVoiceTemplate, VOICE_TEMPLATES, voiceMethodFor } from '@/config/voiceTemplates'
import { voiceSlotsForAct } from '@/services/voiceSlotFillers'
import { voiceTextForAct } from '@/services/voiceStepSync'
import { voiceSpatialCognition } from '@/services/voiceSpatialCognition'
import {
  resetAbsorptionVoiceKeys,
  voiceCueForAbsorptionDone,
  voiceCueForAbsorptionStart,
} from '@/services/voiceAbsorptionSync'
import { ABSORPTION_VOICE_GUIDE } from '@/config/voiceTemplates'
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

  it('attribution act voice prefers overflow mechanism when present', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const withMech: RunResponse = {
      ...fx,
      phases: {
        ...fx.phases,
        diagnosis: {
          ...(fx.phases?.diagnosis ?? {}),
          overflow_mechanism: { primary: 'discharge_anomaly', status: 'hypothesis' },
        } as RunResponse['phases']['diagnosis'],
        cause: {
          ...(fx.phases?.cause ?? {}),
          overflow_mechanism: { primary: 'discharge_anomaly', status: 'hypothesis' },
          cause_analysis: {
            ...(fx.phases?.cause?.cause_analysis ?? {}),
            primary_cause: '信号控制不当',
          },
        } as RunResponse['phases']['cause'],
      },
    }
    const text = voiceTextForAct(act, withMech)
    expect(text).toContain('判断问题集中在本路口放行过程')
    expect(text).not.toContain('信号控制不当')
  })

  it('evidence-insufficient voice asks for more evidence without jargon', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const response = structuredClone(fx)
    response.phases.diagnosis = {
      ...(response.phases.diagnosis ?? {}),
      overflow_mechanism: { primary: 'evidence_insufficient', status: 'hypothesis' },
    } as RunResponse['phases']['diagnosis']
    const text = voiceTextForAct(act, response)

    expect(text).toContain('待补充更多证据')
    expect(text).not.toContain('补盲')
  })

  it('strategy and plan acts include voice conclusion aligned with decision contract', () => {
    const strategyAct = ACT_DEFS.find((item) => item.id === 'act8_strategy')!
    const planAct = ACT_DEFS.find((item) => item.id === 'act9_plan')!
    const strategyText = voiceTextForAct(strategyAct, fx)
    const planText = voiceTextForAct(planAct, fx)

    expect(strategyText).toContain('治理策略与边界约束')
    expect(strategyText).not.toContain('干线联控约束')
    expect(planText).toContain('配时方案生成')
    expect(planText).not.toContain('核心结论')
  })

  it('voice step titles stay aligned with process titles for all speakable acts', () => {
    for (const act of ACT_DEFS) {
      const def = VOICE_TEMPLATES[act.id]
      expect(def, `missing voice template for ${act.id}`).toBeTruthy()
      expect(def!.stepTitle).toBe(act.processTitle)
      const text = voiceTextForAct(act, fx)
      expect(text).toContain(act.processTitle)
    }
  })

  it('cases act voice gives a qualitative result without reading counts', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act7_cases')!
    const text = voiceTextForAct(act, fx)
    const primary = fx.phases?.cause?.cause_analysis?.primary_cause ?? ''

    expect(text).toContain('案例校验')
    expect(text).toContain('不直接套用历史方案')
    expect(text).not.toMatch(/匹配同类案例\s*\d+|高度相似\s*\d+/)
    if (primary) expect(text).not.toContain(primary.split(/[（(]/)[0]?.trim() ?? primary)
  })

  it('attribution voice purpose reflects post-evidence order', () => {
    const act = ACT_DEFS.find((item) => item.id === 'act4_attribution')!
    const text = voiceTextForAct(act, fx)
    expect(text).toContain('归因分析')
    expect(text).toContain('解释排队为什么形成')
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

  it('uses neutral intersection wording when road axes are not proven', () => {
    const resp = {
      diagnosis_ticket: { intersection_name: '解放东路与奥体中路路口' },
      phases: {
        intent: {
          spatial_scene: {
            target: { inter_name: '解放东路与奥体中路路口' },
            axis_roads: {
              ew_road: null,
              ns_road: null,
              road_pair: ['解放东路', '奥体中路'],
              available: true,
            },
          },
        },
      },
    } as unknown as RunResponse

    expect(voiceSpatialCognition(resp)).toBe('解放东路与奥体中路路口，由解放东路与奥体中路相交')
  })
})

describe('voiceAbsorptionSync', () => {
  it('吸收过程只播一句引导，并在完成时播报实际吸收内容', () => {
    resetAbsorptionVoiceKeys()
    const start = voiceCueForAbsorptionStart('run-1')
    expect(start?.text).toBe(ABSORPTION_VOICE_GUIDE.absorptionStart)
    expect(voiceCueForAbsorptionStart('run-1')).toBeNull()
    const result = {
      ...({} as Parameters<typeof voiceCueForAbsorptionDone>[1]),
      skill_id: 'skill-test',
      absorption: {
        value_snapshot: {
          what: { title: '固化技能', bullets: ['路口：测试路口', '沉淀约束：4 条'] },
          why_rows: [{ key: 'reuse', label: '复用方式', before: '手工检索', after: '按标签自动命中' }],
          delta_rows: [],
        },
      },
    } as unknown as Parameters<typeof voiceCueForAbsorptionDone>[1]
    const done = voiceCueForAbsorptionDone('run-1', result)
    expect(done?.text).toContain('测试路口')
    expect(done?.text).toContain('按标签自动命中')
  })
})
