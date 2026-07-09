import { describe, expect, it } from 'vitest'
import { ACT_DEFS } from '@/composables/useTimeline'
import { composeVoiceAnnounce, renderVoiceTemplate, VOICE_TEMPLATES } from '@/config/voiceTemplates'
import { voiceSlotsForAct } from '@/services/voiceSlotFillers'
import { voiceTextForAct } from '@/services/voiceStepSync'
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
})
