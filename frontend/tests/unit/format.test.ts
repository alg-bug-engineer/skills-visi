import { describe, it, expect } from 'vitest'
import { pct, ratio, meters, num, ratioTone, laneTone, isNum } from '@/utils/format'

describe('format', () => {
  it('pct', () => {
    expect(pct(0.5741)).toBe('57.4%')
    expect(pct(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
  })
  it('ratio / meters / num', () => {
    expect(ratio(1.0873)).toBe('1.09')
    expect(meters(158)).toBe('158m')
    expect(num(0.59, 2)).toBe('0.59')
    expect(ratio(NaN)).toBe('—')
  })
  it('isNum guards non-finite', () => {
    expect(isNum(1)).toBe(true)
    expect(isNum(NaN)).toBe(false)
    expect(isNum(Infinity)).toBe(false)
    expect(isNum('1')).toBe(false)
  })
  it('ratioTone thresholds', () => {
    expect(ratioTone(1.1)).toBe('alarm')
    expect(ratioTone(0.85)).toBe('evidence')
    expect(ratioTone(0.2)).toBe('primary')
    expect(ratioTone(null)).toBe('mute')
  })
  it('laneTone thresholds', () => {
    expect(laneTone(0.95)).toBe('alarm')
    expect(laneTone(0.7)).toBe('evidence')
    expect(laneTone(0.1)).toBe('protected')
    expect(laneTone(undefined)).toBe('mute')
  })
})
