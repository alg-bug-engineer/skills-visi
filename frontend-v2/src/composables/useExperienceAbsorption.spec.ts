import { describe, expect, it } from 'vitest'
import { reduceAbsorptionEvent } from '../composables/useExperienceAbsorption'
import { createInitialAbsorptionState } from '../types/skillAbsorption'

describe('reduceAbsorptionEvent', () => {
  it('appends thought_delta to monologue line', () => {
    const state = createInitialAbsorptionState()
    reduceAbsorptionEvent(
      state,
      {
        event: 'skill_absorption',
        type: 'thought_delta',
        stage: 'recap',
        timestamp: '',
        payload: { delta: '收到固化' },
      },
      1,
    )
    reduceAbsorptionEvent(
      state,
      {
        event: 'skill_absorption',
        type: 'thought_delta',
        stage: 'recap',
        timestamp: '',
        payload: { delta: '指令。' },
      },
      2,
    )
    const line = state.lines.find((item) => item.kind === 'monologue')
    expect(line?.text).toBe('收到固化指令。')
  })

  it('appends evidence chips one at a time', () => {
    const state = createInitialAbsorptionState()
    reduceAbsorptionEvent(
      state,
      {
        event: 'skill_absorption',
        type: 'evidence',
        stage: 'value',
        timestamp: '',
        payload: {
          chip: { key: 'experience.0', label: '沉淀', value: '一线约束：垂直方向不能溢出' },
        },
      },
      1,
    )
    reduceAbsorptionEvent(
      state,
      {
        event: 'skill_absorption',
        type: 'evidence',
        stage: 'value',
        timestamp: '',
        payload: {
          chip: { key: 'experience.1', label: '沉淀', value: '量化意图：max_spillback' },
        },
      },
      2,
    )
    const line = state.lines.find((item) => item.kind === 'evidence')
    expect(line?.chips).toHaveLength(2)
    expect(line?.chips?.[0].key).toBe('experience.0')
  })

  it('activates stacked absorption on start', () => {
    const state = createInitialAbsorptionState()
    reduceAbsorptionEvent(
      state,
      {
        event: 'skill_absorption',
        type: 'skill_absorption_start',
        stage: '',
        timestamp: '',
        payload: { skill_id: 'skill_x', intersection: '测试路口', action: 'CREATE' },
      },
      1,
    )
    expect(state.active).toBe(true)
    expect(state.skillId).toBe('skill_x')
    expect(state.action).toBe('CREATE')
  })
})
