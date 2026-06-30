import { describe, expect, it } from 'vitest'
import { buildNarrativeRuntimeItems, shouldSkipRuntimeMetric } from './narrativeStack'
import type { FlowTimingGovernance, ProblemEvidence } from '../types/evidence'

describe('shouldSkipRuntimeMetric', () => {
  it('skips signal adjustment conclusions', () => {
    expect(shouldSkipRuntimeMetric('信号调整', '增加 0 秒')).toBe(true)
    expect(shouldSkipRuntimeMetric('配时', '增加 0 秒')).toBe(true)
  })
})

describe('buildNarrativeRuntimeItems', () => {
  it('returns empty list when no data', () => {
    expect(buildNarrativeRuntimeItems({})).toEqual([])
  })

  it('omits overall saturation from runtime items', () => {
    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { saturation_rate: 0.92 },
    })
    expect(items.find((i) => i.label === '饱和度')).toBeUndefined()
  })

  it('shows per-approach saturation from cognition metrics_by_arm', () => {
    const items = buildNarrativeRuntimeItems({
      cognition: {
        metrics_by_arm: [
          { dir4_label: '西', saturation: 1.44 },
          { dir4_label: '北', saturation: 0.62 },
        ],
      },
    })
    expect(items.find((i) => i.label === '西进口饱和度')?.value).toContain('1.44')
    expect(items.find((i) => i.label === '北进口饱和度')?.value).toContain('0.62')
    expect(items.find((i) => i.label === '饱和度')).toBeUndefined()
  })

  it('deduplicates approach saturation when HUD sends short approach labels', () => {
    const items = buildNarrativeRuntimeItems({
      dataInsight: {
        title: '运行数据',
        metrics: [
          { label: '东进口', value: '2.87' },
          { label: '南进口', value: '2.87' },
          { label: '西进口', value: '1.94' },
          { label: '北进口', value: '1.28' },
          { label: '延误指数', value: '1.88' },
          { label: '服务水平', value: 'F-阻塞' },
        ],
      },
      cognition: {
        metrics_by_arm: [
          { dir4_label: '东', saturation: 2.87 },
          { dir4_label: '西', saturation: 1.94 },
          { dir4_label: '北', saturation: 1.28 },
        ],
      },
    })

    expect(items.find((i) => i.label === '东进口饱和度')?.value).toContain('2.87')
    expect(items.find((i) => i.label === '西进口饱和度')?.value).toContain('1.94')
    expect(items.find((i) => i.label === '北进口饱和度')?.value).toContain('1.28')
    expect(items.find((i) => i.label === '东进口')).toBeUndefined()
    expect(items.find((i) => i.label === '南进口')).toBeUndefined()
    expect(items.find((i) => i.label === '延误指数')).toBeDefined()
    expect(items.find((i) => i.label === '服务水平')).toBeDefined()
  })

  it('orders items: metrics → imbalance → chronic', () => {
    const evidence = {
      chronic: { is_chronic: true, congested_days: 5, window_days: 7 },
      external_evidence: { complaint_total: 6, complaints: [{ type: '夜间噪音', count: 6 }] },
    } as unknown as ProblemEvidence

    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { imbalance_index: 0.4 },
      dataInsight: {
        title: '运行数据',
        metrics: [
          { label: '饱和度', value: '0.90' },
          { label: '延误指数', value: '1.30' },
          { label: '失衡系数', value: '0.40' },
          { label: '转向极差', value: '0.55' },
          { label: '规则结论', value: '过饱和需增加绿灯' },
        ],
      },
      evidence,
    })

    const categories = items.map((i) => i.category)
    const order = ['metrics', 'imbalance', 'chronic']
    const sortedByOrder = [...categories].sort(
      (a, b) => order.indexOf(a) - order.indexOf(b),
    )
    expect(categories).toEqual(sortedByOrder)

    expect(items.find((i) => i.label === '失衡系数')).toBeUndefined()
    expect(items.find((i) => i.category === 'imbalance')).toBeDefined()
    expect(items.find((i) => i.label === '常发拥堵')).toBeDefined()
    expect(items.find((i) => i.label === '群众投诉')).toBeUndefined()
    expect(items.find((i) => i.label === '转向极差')).toBeUndefined()
    expect(items.find((i) => i.label === '规则结论')).toBeUndefined()
    expect(items.find((i) => i.label === '干线绿波')).toBeUndefined()
  })

  it('skips duplicate saturation metric rows', () => {
    const items = buildNarrativeRuntimeItems({
      runtimeMetrics: { saturation_rate: 0.7 },
      dataInsight: { title: '运行数据', metrics: [{ label: '饱和度', value: '0.99' }] },
    })
    expect(items.filter((i) => i.label === '饱和度')).toHaveLength(0)
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
    expect(items.find((i) => i.label === '干线绿波')).toBeUndefined()
    expect(items.find((i) => i.label === '节点位置')).toBeUndefined()
  })

  it('shows all turn-level metrics from evidence.by_turn', () => {
    const items = buildNarrativeRuntimeItems({
      evidence: {
        by_turn: [
          { label: '东左转', turn_saturation: 1.77, green_utilization: 1.77 },
          { label: '西直行', turn_saturation: 0.03, green_utilization: 0.35 },
        ],
      } as ProblemEvidence,
    })
    expect(items.find((i) => i.label === '东左转饱和度')?.value).toContain('1.77')
    expect(items.find((i) => i.label === '西直行饱和度')?.value).toContain('0.03')
    expect(items.find((i) => i.label === '西直行绿灯利用')?.value).toBe('0.35')
  })

  it('uses turn-level saturation instead of approach aggregates when map labels are turn-driven', () => {
    const items = buildNarrativeRuntimeItems({
      cognition: {
        metrics_by_arm: [
          { dir4_label: '东', saturation: 2.87 },
          { dir4_label: '西', saturation: 1.94 },
          { dir4_label: '北', saturation: 1.28 },
        ],
      },
      evidence: {
        by_turn: [
          { label: '东左转', turn_saturation: 1.83, green_utilization: 1.84 },
          { label: '北直行', turn_saturation: 0.9, green_utilization: 0.9 },
        ],
      } as ProblemEvidence,
    })

    expect(items.find((i) => i.label === '东进口饱和度')).toBeUndefined()
    expect(items.find((i) => i.label === '西进口饱和度')).toBeUndefined()
    expect(items.find((i) => i.label === '北进口饱和度')).toBeUndefined()
    expect(items.find((i) => i.label === '东左转饱和度')?.value).toContain('1.83')
    expect(items.find((i) => i.label === '北直行饱和度')?.value).toContain('0.90')
  })

  it('shows turn-level metrics from flow timing governance turn_balance when no by_turn', () => {
    const governance = {
      match_verdict: 'mismatch',
      primary_diagnosis: {
        type: 'timing_optimizable',
        headline:
          '东左转已过饱和（饱和1.77、绿灯利用177%），而北左转绿灯利用率仅26%仍有富余——属于绿灯分配不均，配时可改善',
        lever: '建议挪绿',
        severity: 'high',
        evidence: [],
        structure_limited: false,
        turn_balance: {
          over: { label: '东左转', turn_saturation: 1.77, green_utilization: 1.77 },
          spare: { label: '北左转', turn_saturation: 0.45, green_utilization: 0.26 },
        },
      },
    } as FlowTimingGovernance

    const items = buildNarrativeRuntimeItems({
      dataInsight: { title: '运行数据', metrics: [{ label: '延误指数', value: '1.89' }] },
      flowTimingGovernance: governance,
    })

    expect(items.find((i) => i.label === '东左转饱和度')?.value).toContain('1.77')
    expect(items.find((i) => i.label === '东左转绿灯利用')?.value).toBe('1.77')
    expect(items.find((i) => i.label === '北左转绿灯利用')?.value).toBe('0.26')
    expect(items.find((i) => i.label === '信号调整')).toBeUndefined()
  })

  it('filters conclusion metrics from data insight buffer', () => {
    const items = buildNarrativeRuntimeItems({
      dataInsight: {
        title: '治理建议 · 证据链',
        metrics: [
          { label: '信号调整', value: '增加 0 秒' },
          { label: '延误指数', value: '1.30' },
        ],
      },
    })
    expect(items.find((i) => i.label === '信号调整')).toBeUndefined()
    expect(items.find((i) => i.label === '延误指数')).toBeDefined()
  })
})
