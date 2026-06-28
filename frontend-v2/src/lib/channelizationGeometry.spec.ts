import { describe, it, expect } from 'vitest'
import {
  metersToLngLat,
  geoBearing,
  angleDiff,
  armAngleFromLink,
  parseLaneInfo,
  gatherArms,
  calcBoxR,
  laneColor,
  laneLabel,
  arrowSvg,
  linkPath,
  MOVE_COLOR,
  type ChannelLink,
} from './channelizationGeometry'

const C: [number, number] = [117.111376, 36.659469]

describe('metersToLngLat', () => {
  it('沿臂朝外 70m 距中心约 70m', () => {
    const [lng, lat] = metersToLngLat(C, 70, 0, 90)
    const dx = (lng - C[0]) * Math.cos((C[1] * Math.PI) / 180) * 111320
    const dy = (lat - C[1]) * 111320
    expect(Math.hypot(dx, dy)).toBeCloseTo(70, 0)
  })
  it('右行：进口道(-v 左)落在出口道(+v 右)北侧（东臂 bearing≈87）', () => {
    const br = 87.2
    const entr = metersToLngLat(C, 30, -1.65, br)
    const exit = metersToLngLat(C, 30, 1.65, br)
    expect(entr[1]).toBeGreaterThan(exit[1])
  })
})

describe('geoBearing / angleDiff', () => {
  it('正东方向≈90°', () => {
    expect(geoBearing([117, 36], [117.001, 36])).toBeCloseTo(90, 0)
  })
  it('正北方向≈0°', () => {
    expect(geoBearing([117, 36], [117, 36.001])).toBeCloseTo(0, 0)
  })
  it('angleDiff 取 0-180', () => {
    expect(angleDiff(10, 350)).toBeCloseTo(20, 5)
    expect(angleDiff(0, 180)).toBeCloseTo(180, 5)
  })
})

describe('linkPath', () => {
  it('解析 WKT geom', () => {
    expect(linkPath({ geom: 'LINESTRING(117.1 36.6, 117.2 36.7)' } as ChannelLink)).toEqual([
      [117.1, 36.6],
      [117.2, 36.7],
    ])
  })
  it('优先用 path 数组', () => {
    expect(linkPath({ path: [[1, 2], [3, 4]] } as unknown as ChannelLink)).toEqual([[1, 2], [3, 4]])
  })
})

describe('armAngleFromLink', () => {
  it('进口：由贴近路口点指向外侧（东进口≈87）', () => {
    const lk: ChannelLink = {
      link_role: 'entrance',
      path: [
        [117.113399, 36.659564],
        [117.111474, 36.659489],
      ],
    }
    expect(armAngleFromLink(lk)).toBeCloseTo(87, 0)
  })
  it('无 path 时回退角度（进口用 (t_angle+180)%360）', () => {
    expect(armAngleFromLink({ link_role: 'entrance', t_angle: 267 } as ChannelLink)).toBeCloseTo(87, 0)
    expect(armAngleFromLink({ link_role: 'exit', f_angle: 87 } as ChannelLink)).toBeCloseTo(87, 0)
  })
})

describe('parseLaneInfo / 配色 / 标签', () => {
  it('拆分车道码', () => {
    expect(parseLaneInfo({ lane_info: 'B|B|C|D' } as ChannelLink)).toEqual(['B', 'B', 'C', 'D'])
  })
  it('lane_info 缺失按车道数填直行', () => {
    expect(parseLaneInfo({ c_lane_num: 3 } as ChannelLink)).toEqual(['C', 'C', 'C'])
  })
  it('单一/组合配色', () => {
    expect(laneColor('B')).toBe(MOVE_COLOR.left)
    expect(laneColor('C')).toBe(MOVE_COLOR.straight)
    expect(laneColor('D')).toBe(MOVE_COLOR.right)
    expect(laneColor('A')).toBe(MOVE_COLOR.uturn)
    expect(laneColor('CD')).toBe(MOVE_COLOR.mixed)
    expect(laneColor('AB')).toBe(MOVE_COLOR.mixed)
  })
  it('车道功能中文标签', () => {
    expect(laneLabel('AB')).toBe('掉头左转')
    expect(laneLabel('CD')).toBe('直行右转')
    expect(laneLabel('C')).toBe('直行')
  })
})

describe('gatherArms / calcBoxR', () => {
  const links: ChannelLink[] = [
    { link_role: 'entrance', lane_info: 'B|C|D', path: [[117.114, 36.6595], [117.1115, 36.65949]] },
    { link_role: 'exit', lane_info: 'C|C', c_lane_num: 2, path: [[117.1115, 36.65945], [117.114, 36.6594]] },
  ]
  it('同向进出口归为一臂', () => {
    const arms = gatherArms(links)
    expect(arms).toHaveLength(1)
    expect(arms[0].inLink).toBeTruthy()
    expect(arms[0].outLink).toBeTruthy()
  })
  it('多进口取最宽为臂主进口', () => {
    const more: ChannelLink[] = [
      ...links,
      { link_role: 'entrance', lane_info: 'C|D', path: [[117.114, 36.65951], [117.1115, 36.6595]] },
    ]
    const arms = gatherArms(more)
    expect(arms).toHaveLength(1)
    expect(parseLaneInfo(arms[0].inLink!)).toHaveLength(3)
  })
  it('boxR 在合理范围', () => {
    const r = calcBoxR(gatherArms(links))
    expect(r).toBeGreaterThanOrEqual(18)
    expect(r).toBeLessThanOrEqual(60)
  })
})

describe('arrowSvg', () => {
  it('返回 data-uri', () => {
    expect(arrowSvg('C', '#fff')).toMatch(/^data:image\/svg\+xml/)
  })
  it('组合码包含多段路径（直行+右转 2 个箭头头）', () => {
    const svg = decodeURIComponent(arrowSvg('CD', '#fff'))
    // 直行主杆 + 右转分支 → 至少 2 个 stroke 段
    expect((svg.match(/M/g) || []).length).toBeGreaterThanOrEqual(3)
  })
  it('掉头码包含半环 Q 曲线', () => {
    const svg = decodeURIComponent(arrowSvg('A', '#fff'))
    expect(svg).toContain('Q')
  })
})
