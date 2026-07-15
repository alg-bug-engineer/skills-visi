import { describe, expect, it } from 'vitest'
import { selectArmsForMetricLabels } from '@/map/channelizationLayer'
import type { ChannelArm } from '@/map/channelizationGeometry'

function arm(saturation: number, queue_m = 0): ChannelArm {
  return {
    angle: 0,
    inLink: {
      link_role: 'entrance',
      metrics: { saturation, queue_m },
    },
    outLink: null,
  }
}

describe('channelization metric label density', () => {
  it('keeps at most two highest-severity approach metric cards', () => {
    const arms = [arm(0.4), arm(0.95), arm(0.7), arm(1.1)]
    const selected = selectArmsForMetricLabels(arms, 2)
    expect(selected.size).toBe(2)
    expect(selected.has(arms[3])).toBe(true)
    expect(selected.has(arms[1])).toBe(true)
    expect(selected.has(arms[0])).toBe(false)
  })
})
