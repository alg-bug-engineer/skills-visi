import { describe, it, expect } from 'vitest'
import { applyPhaseHighlight, type PhaseHighlightTarget } from './channelizationPhase'
import type { CognitionPayload } from '../types/map'

/** 记录各 apply* 调用的假渠化层 */
function makeFakeLayer() {
  const calls: Record<string, unknown[][]> = {
    clearCheck: [],
    applyTurnHighlight: [],
    applyTurnSaturationLabels: [],
    applyCheckHighlight: [],
    applyDirectionRoleHighlight: [],
    applyArmSceneLabels: [],
    applyQueueLengthHighlight: [],
  }
  const layer: PhaseHighlightTarget = {
    clearCheck: () => calls.clearCheck.push([]),
    applyTurnHighlight: (s) => calls.applyTurnHighlight.push([s]),
    applyTurnSaturationLabels: (s) => calls.applyTurnSaturationLabels.push([s]),
    applyCheckHighlight: (a, b, c) => calls.applyCheckHighlight.push([a, b, c]),
    applyDirectionRoleHighlight: (a, b) => calls.applyDirectionRoleHighlight.push([a, b]),
    applyArmSceneLabels: (a) => calls.applyArmSceneLabels.push([a]),
    applyQueueLengthHighlight: (a) => calls.applyQueueLengthHighlight.push([a]),
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
    expect(calls.applyArmSceneLabels).toHaveLength(1)
    expect(calls.applyArmSceneLabels[0][0]).toEqual([])
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
    expect(calls.applyArmSceneLabels).toHaveLength(2)
    expect(calls.applyArmSceneLabels[1][0]).toEqual([])
  })

  it('traffic 阶段有转向数据时用路臂标签，不叠车道转向饱和度卡', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: true,
      cognition: {
        ...COG,
        metrics_by_turn: [
          { label: '西直行', dir4_label: '西', turn_dir_no: 2, turn_saturation: 0.03 },
        ],
      },
    })
    expect(calls.applyTurnSaturationLabels).toHaveLength(0)
    expect(calls.applyArmSceneLabels).toHaveLength(2)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(1)
  })

  it('traffic 阶段不在渠化臂标上展示饱和度数值', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: true,
      cognition: {
        ...COG,
        direction_groups: [
          { group: '南北向', saturation_max: 1.2, arm_labels: ['南', '北'] },
        ],
      },
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ line2: string }>
    expect(labels?.every((l) => !/^[\d.]+$/.test(l.line2.trim()))).toBe(true)
  })

  it('direction 阶段展示分向饱和度臂标', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'direction',
      allowRuntimeMetrics: true,
      cognition: {
        ...COG,
        direction_groups: [
          { group: '南北向', saturation_max: 1.2, arm_labels: ['南', '北'] },
        ],
      },
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ line2: string }>
    expect(labels?.some((l) => l.line2.includes('1.2'))).toBe(true)
  })

  it('traffic 阶段剥离饱和度后不保留无排队信息的转向占位标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: true,
      cognition: COG,
      activeDimensions: ['flow'],
      sceneMarkers: [
        {
          id: 't-n',
          lon: 117.11,
          lat: 36.66,
          kind: 'metric',
          variant: 'turn',
          title: '北直行',
          value: '1.33',
          dir: '北',
          severity: 'high',
        },
      ],
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ line1: string; line2: string }>
    expect(labels?.some((l) => l.line1 === '北直行')).toBe(false)
    expect(labels?.some((l) => l.line2 === '—')).toBe(false)
  })

  it('direction 阶段转向饱和度展示问题提示文案', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'direction',
      allowRuntimeMetrics: true,
      cognition: COG,
      sceneMarkers: [
        {
          id: 't-n',
          lon: 117.11,
          lat: 36.66,
          kind: 'metric',
          variant: 'turn',
          title: '北直行',
          value: '1.33',
          dir: '北',
          severity: 'high',
        },
      ],
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ line1: string; line2: string }>
    const north = labels?.find((l) => l.line1 === '北直行')
    expect(north?.line2).toContain('过饱和')
    expect(north?.line2).toContain('1.33')
  })

  it('direction 阶段可叠加排队长度文字', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'direction',
      allowRuntimeMetrics: true,
      cognition: COG,
      activeDimensions: ['flow', 'queue'],
      sceneMarkers: [
        {
          id: 't-e',
          lon: 117.11,
          lat: 36.66,
          kind: 'metric',
          variant: 'turn',
          title: '东直行',
          value: '1.10',
          dir: '东',
          severity: 'high',
        },
      ],
      queueArms: [
        { armAngle: 0, queueM: 146, satPct: 110, satRatio: 1.1, dir4: '东', label: '东进口' },
      ],
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ dir: string; line2: string }>
    const east = labels?.find((l) => l.dir === '东')
    expect(east?.line2).toContain('排队')
    expect(east?.line2).toContain('146')
  })

  it('运行数据未揭示时 traffic 阶段不展示饱和度车道卡', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: false,
      cognition: {
        ...COG,
        metrics_by_turn: [
          { label: '西直行', dir4_label: '西', turn_dir_no: 2, turn_saturation: 0.03 },
        ],
      },
    })
    expect(calls.clearCheck).toHaveLength(1)
    expect(calls.applyTurnSaturationLabels).toHaveLength(0)
    expect(calls.applyArmSceneLabels).toHaveLength(1)
    expect(calls.applyArmSceneLabels[0][0]).toEqual([])
  })

  it('saturation 阶段无饱和度 → 提前返回（不调用角色/臂标签）', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, { phase: 'saturation', cognition: COG })
    expect(calls.applyCheckHighlight).toHaveLength(0)
    expect(calls.applyDirectionRoleHighlight).toHaveLength(0)
    expect(calls.applyArmSceneLabels).toHaveLength(1)
    expect(calls.applyArmSceneLabels[0][0]).toEqual([])
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
    expect(calls.applyArmSceneLabels).toHaveLength(2)
  })

  it('路口结构阶段不展示排队标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'links',
      allowRuntimeMetrics: true,
      cognition: COG,
      activeDimensions: ['flow', 'queue'],
      queueArms: [
        { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东', label: '东进口' },
      ],
    })
    expect(calls.applyArmSceneLabels.at(-1)?.[0]).toEqual([])
  })

  it('排队维度相关时仅在 traffic 且运行数据揭示后叠加排队标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: true,
      cognition: COG,
      activeDimensions: ['flow', 'queue'],
      queueArms: [
        { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东', label: '东进口' },
      ],
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ dir: string; line2: string }>
    const east = labels?.find((l) => l.dir === '东')
    expect(east?.line2).toContain('排队~85m')
    expect(east?.line2).not.toContain('饱和')
    expect(calls.applyQueueLengthHighlight).toHaveLength(1)
    expect((calls.applyQueueLengthHighlight[0][0] as Array<{ queueM: number }>)[0]?.queueM).toBe(85)
  })

  it('运行数据未揭示时不叠加排队标签', () => {
    const { layer, calls } = makeFakeLayer()
    applyPhaseHighlight(layer, {
      phase: 'traffic',
      allowRuntimeMetrics: false,
      cognition: COG,
      activeDimensions: ['flow', 'queue'],
      queueArms: [
        { armAngle: 0, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '东', label: '东进口' },
      ],
    })
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ dir: string; line2: string }>
    expect(labels?.some((l) => l.line2.includes('排队'))).toBe(false)
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
    const labels = calls.applyArmSceneLabels.at(-1)?.[0] as Array<{ dir: string; line2: string }>
    expect(labels?.some((l) => l.line2.includes('排队'))).toBe(false)
  })
})
