import { describe, expect, it } from 'vitest'
import { ACT_DEFS, summaryFor } from '@/composables/useTimeline'
import { composeVoiceAnnounce, renderVoiceTemplate, VOICE_TEMPLATES } from '@/config/voiceTemplates'
import { voiceMethodFor } from '@/config/actDomainCopy'
import { voiceSlotsForAct } from '@/services/voiceSlotFillers'
import { voiceTextForAct } from '@/services/voiceStepSync'
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

  it('strategy plan and feedback acts omit voice conclusion', () => {
    for (const id of ['act7_strategy', 'act8_plan', 'act9_feedback'] as const) {
      const act = ACT_DEFS.find((item) => item.id === id)!
      const text = voiceTextForAct(act, fx)
      const summary = summaryFor(act, fx)

      expect(text).not.toContain('核心结论')
      expect(text).not.toContain(summary)
    }
  })
})
