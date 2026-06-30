import { describe, expect, it } from 'vitest'
import { severityLevel, severityColor } from './ringSeverity'

describe('severityLevel', () => {
  it('aligns with backend _severity thresholds', () => {
    expect(severityLevel(0.95)).toBe('high')
    expect(severityLevel(0.85)).toBe('high')
    expect(severityLevel(0.7)).toBe('medium')
    expect(severityLevel(0.65)).toBe('medium')
    expect(severityLevel(0.5)).toBe('low')
  })
  it('returns unknown for null/undefined', () => {
    expect(severityLevel(null)).toBe('unknown')
    expect(severityLevel(undefined)).toBe('unknown')
  })
})

describe('severityColor', () => {
  it('maps saturation to severity color', () => {
    expect(severityColor(0.95)).toBe('#ff6b4a')
    expect(severityColor(0.7)).toBe('#ffaa44')
    expect(severityColor(0.4)).toBe('#6dffb5')
    expect(severityColor(null)).toBe('#3a4a66')
  })
})
