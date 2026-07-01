import { describe, expect, it } from 'vitest'
import { cognitionDisplaySummary, solutionDisplayText, stripMarkdown } from './textFormat'

describe('textFormat', () => {
  it('strips markdown bold', () => {
    expect(stripMarkdown('主要方向绿灯时长**+0 秒**')).toBe('主要方向绿灯时长+0 秒')
  })

  it('prefers structured cognition summary', () => {
    expect(
      cognitionDisplaySummary({
        text: '晚高峰东进口排队',
        structured: { summary: '晚高峰东进口左转排队很长' },
      }),
    ).toBe('晚高峰东进口左转排队很长')
  })

  it('prefers solution_summary over raw formula', () => {
    expect(
      solutionDisplayText({
        solution_summary: '为东左转增加有效绿灯约 8 秒',
        quantified: 'min(traffic_flow.saturation_rate * 12, 25)',
      }),
    ).toBe('为东左转增加有效绿灯约 8 秒')
  })
})
