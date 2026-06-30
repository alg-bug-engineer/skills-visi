import { describe, expect, it } from 'vitest'
import { normalizeTurnMetrics, turnSatLabelsFromMetrics } from './turnMetrics'

describe('turnMetrics', () => {
  it('normalizes by_turn rows with dir and turn char', () => {
    const rows = normalizeTurnMetrics([
      { label: '西直行', dir8_code: 6, turn_dir_no: 2, turn_saturation: 0.03, green_utilization: 0.35 },
    ])
    expect(rows[0].dir4_label).toBe('西')
    expect(rows[0].turn).toBe('直')
  })

  it('builds lane label specs for channelization', () => {
    const specs = turnSatLabelsFromMetrics(
      normalizeTurnMetrics([
        { label: '西直行', turn_dir_no: 2, turn_saturation: 0.03 },
      ]),
    )
    expect(specs[0].dir).toBe('西')
    expect(specs[0].turnCode).toBe('C')
    expect(specs[0].saturation).toBe(0.03)
  })
})
