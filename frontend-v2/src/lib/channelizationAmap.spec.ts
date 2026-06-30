import { describe, it, expect, beforeEach } from 'vitest'
import { ChannelizationAmapLayer, armMatchesDir, type ChannelInterItem } from './channelizationAmap'

/* ── AMap stub ─────────────────────────────────────────────────────────────── */
class StubOverlay {
  shown = true
  type: string
  opt: any
  constructor(type: string, opt: any) {
    this.type = type
    this.opt = opt
  }
  show() {
    this.shown = true
  }
  hide() {
    this.shown = false
  }
}
function makeAmapStub() {
  const mk = (type: string) => function (opt: any) {
    return new StubOverlay(type, opt)
  }
  return {
    Polygon: mk('Polygon'),
    Polyline: mk('Polyline'),
    Marker: mk('Marker'),
    Circle: mk('Circle'),
    CircleMarker: mk('CircleMarker'),
    Icon: function (o: any) {
      return o
    },
    Size: function () {},
    Pixel: function () {},
  }
}
function makeMapStub() {
  const added: StubOverlay[] = []
  let zoom = 18
  return {
    added,
    setZoom(z: number) {
      zoom = z
    },
    getZoom: () => zoom,
    add: (o: StubOverlay) => added.push(o),
    remove: (os: StubOverlay | StubOverlay[]) => {
      const arr = Array.isArray(os) ? os : [os]
      for (const o of arr) {
        const i = added.indexOf(o)
        if (i >= 0) added.splice(i, 1)
      }
    },
  }
}

/* ── 真实奥体西路×经十路（简化两臂，足够覆盖逻辑） ─────────────────────────── */
const INTER: ChannelInterItem = {
  intersection_info: { longitude: 117.111376, latitude: 36.659469, name: '奥体西路与经十路路口' },
  surrounding_links: {
    进入路口的路段: [
      {
        lane_info: 'B|B|C|C|C|C|C|D|D',
        c_lane_num: 9,
        lane_num: 9,
        path: [
          [117.108743, 36.659194],
          [117.111281, 36.659242],
        ],
      } as any, // 西进口
      {
        lane_info: 'B|B|B|C|C|C|C|C|C|C',
        c_lane_num: 10,
        lane_num: 10,
        path: [
          [117.113399, 36.659564],
          [117.111474, 36.659489],
        ],
      } as any, // 东进口
    ],
    离开路口的路段: [
      {
        lane_info: 'C|C|C|C|C|C|C',
        c_lane_num: 7,
        lane_num: 7,
        path: [
          [117.111484, 36.659253],
          [117.114258, 36.659387],
        ],
      } as any, // 东出口
    ],
  },
}

describe('ChannelizationAmapLayer 静态渲染', () => {
  let amap: any
  let map: ReturnType<typeof makeMapStub>
  let layer: ChannelizationAmapLayer
  beforeEach(() => {
    amap = makeAmapStub()
    map = makeMapStub()
    layer = new ChannelizationAmapLayer(amap, map, INTER)
    layer.render()
  })

  it('归臂正确（西进口/东进口归两臂）', () => {
    expect(layer.arms.length).toBeGreaterThanOrEqual(2)
  })

  it('进口车道数 = 箭头 Marker 数', () => {
    const arrowMarkers = map.added.filter((o) => o.type === 'Marker' && o.opt.icon)
    const totalIn = layer.arms.reduce((s, a) => s + (a.inLink ? a.inLink.lane_info!.split('|').length : 0), 0)
    expect(arrowMarkers.length).toBe(totalIn)
  })

  it('生成停止线/斑马线/车道面等覆盖物', () => {
    const polys = map.added.filter((o) => o.type === 'Polygon')
    const lines = map.added.filter((o) => o.type === 'Polyline')
    expect(polys.length).toBeGreaterThan(0)
    expect(lines.length).toBeGreaterThan(0)
  })

  it('LOD：低 zoom 隐藏 L2', () => {
    layer.applyLOD(14)
    expect(layer.getLevel()).toBe('L0')
    const laneFace = map.added.find((o) => o.type === 'Polygon' && o.opt.zIndex === 16)
    expect(laneFace?.shown).toBe(false)
    layer.applyLOD(19)
    expect(layer.getLevel()).toBe('L2')
    expect(laneFace?.shown).toBe(true)
  })
})

describe('阶段标注', () => {
  let amap: any
  let map: ReturnType<typeof makeMapStub>
  let layer: ChannelizationAmapLayer
  beforeEach(() => {
    amap = makeAmapStub()
    map = makeMapStub()
    layer = new ChannelizationAmapLayer(amap, map, INTER)
    layer.render()
  })

  it('applyCheckHighlight 生成强调面 + 文本框含指标', () => {
    const before = map.added.length
    layer.applyCheckHighlight('saturation', 'fail', { saturation_max: 0.95 })
    expect(map.added.length).toBeGreaterThan(before)
    const textMarker = map.added.find((o) => o.type === 'Marker' && typeof o.opt.content === 'string' && o.opt.content.includes('饱和度'))
    expect(textMarker).toBeTruthy()
  })

  it('clearHighlight 后再标注不残留旧高亮', () => {
    layer.applyCheckHighlight('saturation', 'fail', { saturation_max: 0.95 })
    const n1 = map.added.length
    layer.applyCheckHighlight('imbalance', 'warn', { unbalance_index: 0.4 })
    // 第二次会先清掉第一次，再加自身；不应无限累加
    const textMarkers = map.added.filter((o) => o.type === 'Marker' && typeof o.opt.content === 'string')
    expect(textMarkers.length).toBe(1)
    expect(textMarkers[0].opt.content).toContain('失衡')
    expect(map.added.length).toBeLessThanOrEqual(n1 + 6)
  })

  it('applyTurnHighlight 生成车道色带 + 黄环 + 文本框', () => {
    layer.applyTurnHighlight({ dir: '西', turnCode: 'B', label: '西左转', saturation: 1.1 })
    const ring = map.added.find((o) => o.type === 'CircleMarker')
    const text = map.added.find((o) => o.type === 'Marker' && typeof o.opt.content === 'string' && o.opt.content.includes('西左转'))
    expect(ring).toBeTruthy()
    expect(text).toBeTruthy()
  })

  it('applyDirectionRoleHighlight 关注/保护各生成强调面', () => {
    layer.applyDirectionRoleHighlight(['西'], ['东'])
    const faces = map.added.filter((o) => o.type === 'Polygon' && o.opt.zIndex === 38)
    expect(faces.length).toBe(layer.arms.length)
  })

  it('applyQueueLengthHighlight 生成排队色带与末端线', () => {
    const before = map.added.length
    layer.applyQueueLengthHighlight([
      { armAngle: 270, queueM: 85, satPct: 95, satRatio: 0.95, dir4: '西', label: '西进口' },
    ])
    expect(map.added.length).toBeGreaterThan(before)
    const band = map.added.find((o) => o.type === 'Polygon' && o.opt.zIndex === 41)
    const endLine = map.added.find((o) => o.type === 'Polyline' && o.opt.zIndex === 42)
    expect(band).toBeTruthy()
    expect(endLine).toBeTruthy()
  })

  it('applyArmSceneLabels 生成臂外缘文本框', () => {
    layer.clearHighlight()
    layer.applyArmSceneLabels([{ dir: '西', line1: '西进口', line2: '饱和 95%', colorHex: '#00e5ff' }])
    const text = map.added.find((o) => o.type === 'Marker' && typeof o.opt.content === 'string' && o.opt.content.includes('西进口'))
    expect(text).toBeTruthy()
  })

  it('dispose 清空所有覆盖物', () => {
    layer.applyCheckHighlight('saturation', 'fail', { saturation_max: 0.95 })
    layer.dispose()
    expect(map.added.length).toBe(0)
  })
})

describe('armMatchesDir', () => {
  it('东臂(87°)匹配东，不匹配南', () => {
    expect(armMatchesDir(87, '东')).toBe(true)
    expect(armMatchesDir(87, '南')).toBe(false)
  })
})
