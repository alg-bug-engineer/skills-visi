import { describe, expect, it } from 'vitest'
import { TraceLayer } from '@/map/traceLayer'

class FakeOverlay {
  options: Record<string, unknown>
  map: unknown

  constructor(options: Record<string, unknown>) {
    this.options = options
  }

  setMap(map: unknown) {
    this.map = map
  }

  on() {}
}

class FakePixel {
  constructor(
    public x: number,
    public y: number,
  ) {}
}

describe('downstream all-turn trace rendering', () => {
  it('keeps multiple turn edges to the same downstream and merges their label', () => {
    const polylines: FakeOverlay[] = []
    const markers: FakeOverlay[] = []
    const amap = {
      Polyline: class extends FakeOverlay {
        constructor(options: Record<string, unknown>) {
          super(options)
          polylines.push(this)
        }
      },
      Marker: class extends FakeOverlay {
        constructor(options: Record<string, unknown>) {
          super(options)
          markers.push(this)
        }
      },
      Pixel: FakePixel,
    }
    const layer = new TraceLayer(amap, {})

    layer.renderDownstreamTraces([
      {
        downstream_inter_id: 'D1',
        name: '共同下游',
        turn_label: '左转',
        turn_dir_no: 1,
        share_pct: 30,
        path: [
          [117.1, 36.6],
          [117.2, 36.7],
        ],
        lon: 117.2,
        lat: 36.7,
      },
      {
        downstream_inter_id: 'D1',
        name: '共同下游',
        turn_label: '右转',
        turn_dir_no: 3,
        share_pct: 15,
        path: [
          [117.1, 36.6],
          [117.2, 36.7],
        ],
        lon: 117.2,
        lat: 36.7,
      },
    ])

    // 每条关系均保留 glow + core，不因下游节点 ID 相同被幂等逻辑吞掉。
    expect(polylines).toHaveLength(4)
    // 一个物理节点 + 一个聚合标签，避免同坐标标签互相遮盖。
    expect(markers).toHaveLength(2)
    const labelHtml = String(markers[1]?.options.content)
    expect(labelHtml).toContain('共同下游')
    expect(labelHtml).toContain('左转')
    expect(labelHtml).toContain('右转')
  })
})
