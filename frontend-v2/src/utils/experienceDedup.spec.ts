import { describe, expect, it } from 'vitest'
import {
  dedupeExperienceSediment,
  filterReusedExperienceBadges,
  normalizeExperienceText,
} from './experienceDedup'

describe('experienceDedup', () => {
  it('normalizes reused badge prefix away', () => {
    const n = normalizeExperienceText('复用了 i1 的认知经验：晚高峰南北向拥堵')
    expect(n).toContain('晚高峰南北向拥堵')
    expect(n).not.toContain('复用了')
  })

  it('dedupes sediment by level and text', () => {
    const out = dedupeExperienceSediment([
      { level: 'cognition', text: '晚高峰 南北向拥堵' },
      { level: 'cognition', text: '晚高峰南北向拥堵' },
      { level: 'diagnosis', text: '学校放学' },
    ])
    expect(out).toHaveLength(2)
  })

  it('filters reused badges overlapping sediment', () => {
    const filtered = filterReusedExperienceBadges(
      ['复用了 x 的认知经验：晚高峰南北向拥堵', '复用了 x 的诊断经验：学校放学'],
      [{ level: 'cognition', text: '晚高峰南北向拥堵', status: 'verified' }],
    )
    expect(filtered).toEqual(['复用了 x 的诊断经验：学校放学'])
  })
})
