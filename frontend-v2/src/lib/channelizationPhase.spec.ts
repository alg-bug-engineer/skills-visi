import { describe, it, expect } from 'vitest'
import { applyPhaseHighlight, type PhaseHighlightTarget } from './channelizationPhase'
import type { CognitionPayload } from '../types/map'

/** 记录各 apply* 调用的假渠化层 */
function makeFakeLayer() {
  const calls: Record<string, unknown[][]> = {
    clearCheck: [],
    applyTurnHighlight: [],
    applyCheckHighlight: [],
    applyDirectionRoleHighlight: [],
    applyArmSceneLabels: [],
  }
  const layer: PhaseHighlightTarget = {
    clearCheck: () => calls.clearCheck.push([]),
    applyTurnHighlight: (s) => calls.applyTurnHighlight.push([s]),
    applyCheckHighlight: (a, b, c) => calls.applyCheckHighlight.push([a, b, c]),
    applyDirectionRoleHighlight: (a, b) => calls.applyDirectionRoleHighlight.push([a, b]),
    applyArmSceneLabels: (a) => calls.applyArmSceneLabels.push([a]),
  }
  return { layer, calls }
}

const COG: CognitionPayload = {
  intersection: { inter_id: 'x', name: '奥体西路与经十路路口', lon: 117.111376, lat: 36.659469 },
  arms: [
    { link_id: 'w', dir4_label: '西', lane_num: 9, lane_info: 'B|B|C|C|C|C|C|D|D' },
    { link_id: 'e', dir4_label: '东', lane_num: 10, lane_info: 'B|B|B|C|C|C|C|C|C|C' },
  ],
}

describe('applyPhaseHighlight', () => {
  it('结构阶段(channelization)只 clearCheck，不叠加任何标注', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, { phase: 'channelization', cognition: COG })
    expect(calls.clearCheck).toHaveLength(1)
    expect(calls.applyCheckHighlight).toHaveLength(0)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(0)
    expect(calls.applyArmSceneLabels).toHaveLength(0)
  })

  it('highlightTurn 非结构阶段 → 走 applyTurnHighlight 并提前返回', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'saturation',
      cognition: COG,
      highlightTurn: { dir: '西', turn: '左', label: '西左转', saturation: 1.1 },
    })
    expect(calls.applyTurnHighlight).toHaveLength(1)
    expect(calls.applyTurnHighlight[0][0]).toMatchObject({ dir: '西', label: '西左转' })
    expect(calls.applyCheckHighlight).toHaveLength(0)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(0)
  })

  it('saturation 阶段有饱和度 → applyCheckHighlight + 角色 + 臂标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'saturation',
      cognition: COG,
      runtimeMetrics: { saturation_rate: 0.95 } as never,
    })
    expect(calls.applyCheckHighlight).toHaveLength(1)
    expect(calls.applyCheckHighlight[0][0]).toBe('saturation')
    expect(calls.applyCheckHighlight[0][1]).toBe('fail') // 0.95 >= 0.85
    expect(calls.applyDirectionRoleHighlight).toHaveLength(1)
    expect(calls.applyArmSceneLabels).toHaveLength(1)
  })

  it('saturation 阶段无饱和度 → 提前返回（不调用角色/臂标签）', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, { phase: 'saturation', cognition: COG })
    expect(calls.applyCheckHighlight).toHaveLength(0)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(0)
    expect(calls.applyArmSceneLabels).toHaveLength(0)
  })

  it('imbalance 阶段有失衡 → applyCheckHighlight(imbalance)', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'imbalance',
      cognition: COG,
      runtimeMetrics: { imbalance_index: 0.4 } as never,
    })
    expect(calls.applyCheckHighlight).toHaveLength(1)
    expect(calls.applyCheckHighlight[0][0]).toBe('imbalance')
  })

  it('direction 阶段 → 角色高亮带 focus/protect', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'direction',
      cognition: COG,
      highlightDirs: ['西'],
      protectedDirs: [],
    })
    expect(calls.applyDirectionRoleHighlight).toHaveLength(1)
    expect(calls.applyDirectionRoleHighlight[0][0]).toEqual(['西'])
  })

  it('traffic 阶段不叠饱和度浮标，但有角色(清空)+臂标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      cognition: COG,
      runtimeMetrics: { saturation_rate: 0.95 } as never,
    })
    expect(calls.applyCheckHighlight).toHaveLength(0)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(1)
    expect(calls.applyDirectionRoleHighlight[0]).toEqual([[], []])
    expect(calls.applyArmSceneLabels).toHaveLength(1)
  })

  it('排队维度相关时叠加排队长度标签（traffic）', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      cognition: COG,
      activeDimensions: ['flow', 'queue'],
      queueArms: [
        { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东', label: '东进口' },
      ],
    })
    const labels = calls.applyArmSceneLabels[0][0] as Array<{ dir: string; line2: string }>
    const east = labels.find((l) => l.dir === '东')
    expect(east?.line2).toContain('排队~85m')
  })

  it('排队维度不相关时不叠加排队标签（如空放：activeDimensions 无 queue）', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      cognition: COG,
      activeDimensions: ['green_util', 'ring'],
      queueArms: [
        { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东', label: '东进口' },
      ],
    })
    const labels = calls.applyArmSceneLabels[0][0] as Array<{ dir: string; line2: string }>
    expect(labels.some((l) => l.line2.includes('排队'))).toBe(false)
  })
})
