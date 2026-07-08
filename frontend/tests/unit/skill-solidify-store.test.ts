import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

describe('presentation store · 固化状态机', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('reset() clears solidifyPhase / skillResult / pendingSolidifyPlanId', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'building'
    s.skillResult = result
    s.pendingSolidifyPlanId = 'downstream_protection'

    s.reset()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.pendingSolidifyPlanId).toBeNull()
    expect(s.dock).toBe('input')
  })

  it('declineSolidify() returns to input dock and idle phase', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'prompt'
    s.dock = 'plan'
    s.skillResult = result

    s.declineSolidify()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.dock).toBe('input')
    expect(s.toast).toContain('已返回主页')
  })

  it('finishSolidify() returns to input dock and idle phase', () => {
    const s = usePresentationStore()
    s.solidifyPhase = 'completed'
    s.dock = 'plan'
    s.skillResult = result

    s.finishSolidify()

    expect(s.solidifyPhase).toBe('idle')
    expect(s.skillResult).toBeNull()
    expect(s.dock).toBe('input')
    expect(s.toast).toContain('已固化并入库')
  })

  it('setSolidifyPhase() advances the phase', () => {
    const s = usePresentationStore()
    s.setSolidifyPhase('building')
    expect(s.solidifyPhase).toBe('building')
  })
})
