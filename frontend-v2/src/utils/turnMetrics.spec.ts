import { describe, expect, it } from 'vitest'
import { formatTurnFlowVph, shortTurnLabel, turnFlowLabelsFromMetrics } from './turnMetrics'

describe('turnFlowLabelsFromMetrics', () => {
  it('builds lane label specs from flow_vph', () => {
    const specs = turnFlowLabelsFromMetrics([
      {
        label: '北直行',
        dir4_label: '北',
        turn_dir_no: 2,
        turn: '直',
        flow_vph: 620,
      },
    ])
    expect(specs).toHaveLength(1)
    expect(specs[0].dir).toBe('北')
    expect(specs[0].flowVph).toBe(620)
  })

  it('formats large flow as compact k', () => {
    expect(formatTurnFlowVph(1250)).toBe('1.3k')
    expect(formatTurnFlowVph(620)).toBe('620')
  })

  it('shortens turn labels for lane pills', () => {
    expect(shortTurnLabel('西左转')).toBe('西·左')
    expect(shortTurnLabel('东直行')).toBe('东·直')
  })
})
