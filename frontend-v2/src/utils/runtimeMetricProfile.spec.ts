import { describe, expect, it } from 'vitest'
import { resolvePrimaryProblemType } from './runtimeMetricProfile'

describe('resolvePrimaryProblemType', () => {
  it('prioritizes conflict over congestion', () => {
    expect(resolvePrimaryProblemType(['congestion', 'conflict'])).toBe('conflict')
  })

  it('defaults to congestion when empty', () => {
    expect(resolvePrimaryProblemType([])).toBe('congestion')
  })
})
