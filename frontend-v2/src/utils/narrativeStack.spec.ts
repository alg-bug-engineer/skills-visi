import { describe, expect, it } from 'vitest'
import { buildNarrativeRuntimeItems } from './narrativeStack'
import type { ProblemEvidence } from '../types/evidence'

describe('buildNarrativeRuntimeItems', () => {
  it('returns empty list when no data', () => {
    expect(buildNarrativeRuntimeItems({})).toEqual([])
  })

  it('builds saturation item with tone + severity', () => {
    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { saturation_rate: 0.92 },
    })
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      id: 'saturation',
      label: '饱和度',
      category: 'saturation',
      severity: 'high',
    })
    expect(items[0].value).toContain('0.92')
    expect(items[0].value).toContain('偏高')
  })

  it('orders items: saturation → metrics → imbalance → corridor → complaint', () => {
    const evidence = {
      corridor_context: { in_corridor: true, corridor_name: '经十路', green_wave_break_risk: true },
      chronic: { is_chronic: true, congested_days: 5, window_days: 7 },
      external_evidence: { complaint_total: 6, complaints: [{ type: '夜间噪音', count: 6 }] },
    } as unknown as ProblemEvidence

    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { saturation_rate: 0.9, imbalance_index: 0.4 },
      dataInsight: {
        title: '运行数据',
        metrics: [
          { label: '饱和度', value: '0.90' },
          { label: '延误指数', value: '1.30' },
          { label: '失衡系数', value: '0.40' },
        ],
      },
      evidence,
    })

    const categories = items.map((i) => i.category)
    // 应按类别顺序排列
    const order = ['saturation', 'metrics', 'imbalance', 'corridor', 'complaint']
    const sortedByOrder = [...categories].sort(
      (a, b) => order.indexOf(a) - order.indexOf(b),
    )
    expect(categories).toEqual(sortedByOrder)

    // 失衡系数应归入 imbalance，不重复出现在 metrics
    expect(items.find((i) => i.label === '失衡系数')).toBeUndefined()
    expect(items.find((i) => i.category === 'imbalance')).toBeDefined()
    // 干线 + 常发 + 投诉 都在
    expect(items.find((i) => i.label === '干线绿波')).toBeDefined()
    expect(items.find((i) => i.label === '常发拥堵')).toBeDefined()
    expect(items.find((i) => i.label === '群众投诉')).toBeDefined()
  })

  it('dedupes by label and prefers runtimeMetrics saturation', () => {
    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { saturation_rate: 0.7 },
      dataInsight: { title: '运行数据', metrics: [{ label: '饱和度', value: '0.99' }] },
    })
    const sat = items.filter((i) => i.label === '饱和度')
    expect(sat).toHaveLength(1)
    expect(sat[0].value).toContain('0.70')
  })

  it('omits corridor and delay HUD metrics duplicated elsewhere', () => {
    const items = buildNarrativeRuntimeItems({
      dataInsight: {
        title: '运行数据',
        metrics: [
          { label: '延误指数', value: '1.30' },
          { label: '延误', value: '1.30' },
          { label: '走廊', value: '经十路' },
          { label: '节点位置', value: '3/5' },
        ],
      },
      evidence: {
        corridor_context: { in_corridor: true, corridor_name: '经十路', green_wave_break_risk: false },
      } as ProblemEvidence,
    })
    expect(items.find((i) => i.label === '延误')).toBeUndefined()
    expect(items.find((i) => i.label === '走廊')).toBeUndefined()
    expect(items.find((i) => i.label === '延误指数')).toBeDefined()
    expect(items.find((i) => i.label === '干线绿波')).toBeDefined()
    expect(items.find((i) => i.label === '节点位置')).toBeDefined()
  })

  it('omits corridor when not in a corridor', () => {
    const items = buildNarrativeRuntimeItems({
      evidence: { corridor_context: { in_corridor: false } } as ProblemEvidence,
    })
    expect(items.find((i) => i.category === 'corridor')).toBeUndefined()
  })
})
