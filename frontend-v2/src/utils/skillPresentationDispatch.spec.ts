import { describe, expect, it } from 'vitest'
import {
  isSkillAbsorptionStreamEvent,
  isSkillBuildStreamEvent,
  isSkillStreamBufferedEvent,
  shouldEnqueueAbsorptionPauseGate,
  shouldEnqueueSkillBuildPauseGate,
} from './skillPresentationDispatch'

/** RT-PAUSE-ABS: 流式即时呈现 + 阶段边界 pause gate */
describe('skillPresentationDispatch RT-PAUSE-ABS', () => {
  it('treats thought/file deltas as stream events', () => {
    expect(isSkillAbsorptionStreamEvent('thought_delta')).toBe(true)
    expect(isSkillAbsorptionStreamEvent('evidence')).toBe(true)
    expect(isSkillAbsorptionStreamEvent('stage_start')).toBe(false)
    expect(isSkillBuildStreamEvent('file_delta')).toBe(true)
    expect(isSkillBuildStreamEvent('file_created')).toBe(false)
  })

  it('only enqueues pause gate after stage/file done', () => {
    expect(shouldEnqueueAbsorptionPauseGate('stage_done')).toBe(true)
    expect(shouldEnqueueAbsorptionPauseGate('skill_absorption_start')).toBe(false)
    expect(shouldEnqueueAbsorptionPauseGate('skill_absorption_done')).toBe(false)
    expect(shouldEnqueueSkillBuildPauseGate('file_done')).toBe(true)
    expect(shouldEnqueueSkillBuildPauseGate('file_created')).toBe(false)
    expect(shouldEnqueueSkillBuildPauseGate('skill_build_start')).toBe(false)
  })

  it('identifies stream items for buffered replay pacing', () => {
    expect(
      isSkillStreamBufferedEvent({
        domain: 'absorption',
        event: { type: 'thought_delta', stage: 'recap', payload: { delta: 'x' } },
      }),
    ).toBe(true)
    expect(
      isSkillStreamBufferedEvent({
        domain: 'build',
        event: { type: 'file_delta', stage: 'writing', payload: { delta: 'y', path: 'a.md' } },
      }),
    ).toBe(true)
  })
})
