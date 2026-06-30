import { describe, expect, it } from 'vitest'
import { assignLabelAnchors } from './upstreamLayout'

describe('assignLabelAnchors', () => {
  it('gives adjacent nodes distinct anchors to avoid overlap', () => {
    const a = assignLabelAnchors([{ id: 'a' }, { id: 'b' }, { id: 'c' }])
    expect(a.a).not.toEqual(a.b)
    expect(a.b).not.toEqual(a.c)
  })

  it('pushes hop2 nodes further out', () => {
    const a = assignLabelAnchors([{ id: 'h2', hop: 2 }])
    const [, dy] = a.h2
    expect(Math.abs(dy)).toBeGreaterThan(58)
  })

  it('is deterministic and stable for same input order', () => {
    const input = [{ id: 'x' }, { id: 'y' }]
    expect(assignLabelAnchors(input)).toEqual(assignLabelAnchors(input))
  })

  it('skips empty ids', () => {
    const a = assignLabelAnchors([{ id: '' }, { id: 'ok' }])
    expect(a['']).toBeUndefined()
    expect(a.ok).toBeDefined()
  })
})
