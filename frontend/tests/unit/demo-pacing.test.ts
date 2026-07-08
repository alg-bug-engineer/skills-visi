import { describe, expect, it } from 'vitest'
import {
  DEMO_ACT_DWELL_AFTER_MS,
  DEMO_ACT_DWELL_FIRST_MS,
  DEMO_TYPING_MS,
  actDwellMs,
} from '@/config/demoPacing'

describe('demoPacing', () => {
  it('第二幕起停留明显长于第一幕', () => {
    expect(DEMO_ACT_DWELL_AFTER_MS).toBeGreaterThan(DEMO_ACT_DWELL_FIRST_MS)
    expect(actDwellMs(0, false)).toBe(DEMO_ACT_DWELL_FIRST_MS)
    expect(actDwellMs(1, false)).toBe(DEMO_ACT_DWELL_AFTER_MS)
    expect(actDwellMs(5, false)).toBe(DEMO_ACT_DWELL_AFTER_MS)
  })

  it('instant 路径停留恒为 0（测试/无障碍/自动化不受延时影响）', () => {
    expect(actDwellMs(0, true)).toBe(0)
    expect(actDwellMs(3, true)).toBe(0)
  })

  it('打字间隔为正数', () => {
    expect(DEMO_TYPING_MS).toBeGreaterThan(0)
  })
})
