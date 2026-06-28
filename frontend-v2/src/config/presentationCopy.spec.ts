import { describe, expect, it } from 'vitest'
import {
  formatIntersectionMatchSummary,
  formatSkillReuseLines,
} from '../config/presentationCopy'

describe('presentationCopy', () => {
  it('formats skill reuse with constraint summary', () => {
    const notice =
      '📚 发现沉淀技能：奥体西路与经十路路口 · 晚高峰\n\n历史约束：垂直方向不能溢出\n\n将基于历史经验辅助本次诊断。'
    const { summary, detail } = formatSkillReuseLines(notice, true)
    expect(summary).toContain('垂直方向不能溢出')
    expect(detail).toContain('发现沉淀技能')
  })

  it('formats intersection match summary', () => {
    expect(formatIntersectionMatchSummary('奥体西路与经十路路口')).toContain('已匹配')
  })
})
