import { describe, expect, it } from 'vitest'
import { filterIndustryCases, parseCaseReferenceId } from './caseReference'
import type { IndustryCaseScenario } from '../types/experience'

describe('parseCaseReferenceId', () => {
  it('parses industry ref', () => {
    expect(parseCaseReferenceId('industry:school_zone')).toEqual({
      subTab: 'industry',
      key: 'school_zone',
    })
  })

  it('parses intersection ref', () => {
    expect(parseCaseReferenceId('intersection:inter_001')).toEqual({
      subTab: 'intersection',
      key: 'inter_001',
    })
  })

  it('returns null for unknown/empty', () => {
    expect(parseCaseReferenceId('')).toBeNull()
    expect(parseCaseReferenceId('foo:bar')).toBeNull()
    expect(parseCaseReferenceId('industry:')).toBeNull()
  })
})

function scenario(id: string, name: string, problem: string): IndustryCaseScenario {
  return {
    scenario_id: id,
    scenario_name: name,
    description: '',
    case_count: 1,
    problems: [{ problem, occurrence: 1, symptoms: [], solutions: [] }],
  }
}

describe('filterIndustryCases', () => {
  const list = [
    scenario('school_zone', '学校周边交通组织', '上下学拥堵'),
    scenario('arterial_green_wave', '主干道干线绿波协调', '停车频繁'),
  ]

  it('returns all when query empty', () => {
    expect(filterIndustryCases(list, '  ')).toHaveLength(2)
  })

  it('filters by scenario name', () => {
    const out = filterIndustryCases(list, '学校')
    expect(out).toHaveLength(1)
    expect(out[0].scenario_id).toBe('school_zone')
  })

  it('filters by problem text', () => {
    const out = filterIndustryCases(list, '停车')
    expect(out.map((s) => s.scenario_id)).toEqual(['arterial_green_wave'])
  })
})
