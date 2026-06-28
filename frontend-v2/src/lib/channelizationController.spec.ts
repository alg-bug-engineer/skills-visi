import { describe, it, expect, beforeEach } from 'vitest'
import { createChannelizationController } from './channelizationController'
import type { ChannelInterItem } from './channelizationAmap'

function makeAmapStub() {
  const mk = (type: string) => function (opt: any) {
    return { type, opt, show() {}, hide() {} }
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
  const added: any[] = []
  return {
    added,
    getZoom: () => 18,
    add: (o: any) => added.push(o),
    remove: (os: any) => {
      const arr = Array.isArray(os) ? os : [os]
      for (const o of arr) {
        const i = added.indexOf(o)
        if (i >= 0) added.splice(i, 1)
      }
    },
  }
}

const INTER: ChannelInterItem = {
  intersection_info: { longitude: 117.111376, latitude: 36.659469, name: '奥体西路与经十路路口' },
  surrounding_links: {
    进入路口的路段: [
      { lane_info: 'B|C|D', c_lane_num: 3, path: [[117.114, 36.6595], [117.1115, 36.65949]] } as any,
    ],
    离开路口的路段: [
      { lane_info: 'C|C', c_lane_num: 2, path: [[117.1115, 36.65945], [117.114, 36.6594]] } as any,
    ],
  },
}

describe('channelizationController', () => {
  let amap: any
  let map: ReturnType<typeof makeMapStub>
  beforeEach(() => {
    amap = makeAmapStub()
    map = makeMapStub()
  })

  it('mount 渲染、active、center 可读', () => {
    const ctrl = createChannelizationController(amap, map)
    expect(ctrl.active()).toBe(false)
    ctrl.mount(INTER)
    expect(ctrl.active()).toBe(true)
    expect(ctrl.center).toEqual([117.111376, 36.659469])
    expect(map.added.length).toBeGreaterThan(0)
  })

  it('重复 mount 不泄漏（旧层先 dispose）', () => {
    const ctrl = createChannelizationController(amap, map)
    ctrl.mount(INTER)
    const n1 = map.added.length
    ctrl.mount(INTER)
    expect(map.added.length).toBe(n1)
  })

  it('syncPhase 未 mount 时安全无操作', () => {
    const ctrl = createChannelizationController(amap, map)
    expect(() => ctrl.syncPhase({ phase: 'saturation', cognition: null })).not.toThrow()
  })

  it('dispose 清空地图', () => {
    const ctrl = createChannelizationController(amap, map)
    ctrl.mount(INTER)
    ctrl.dispose()
    expect(map.added.length).toBe(0)
    expect(ctrl.active()).toBe(false)
  })
})
