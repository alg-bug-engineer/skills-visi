import { describe, expect, it } from 'vitest'
import {
  buildCorrelateLabelHtml,
  coverageNodeStyle,
  defaultOpenUpstreamId,
  formatCorrelateFeedDirection,
  isRenderableUpstream,
  MIN_PATH_COVERAGE,
  stripIntersectionSuffix,
} from './upstreamCorrelateLabels'
import type { UpstreamCorrelateMap } from '../types/map'

describe('upstreamCorrelateLabels', () => {
  it('strips trailing 路口 from names', () => {
    expect(stripIntersectionSuffix('姚家南路与浆水泉路路口')).toBe('姚家南路与浆水泉路')
    expect(stripIntersectionSuffix('经十路')).toBe('经十路')
  })

  it('formats feed direction from correlate dir8 and turn', () => {
    expect(formatCorrelateFeedDirection(2, 2)).toBe('东直行')
    expect(formatCorrelateFeedDirection(0, 1)).toBe('北左转')
    expect(formatCorrelateFeedDirection(6, 3)).toBe('西右转')
  })

  it('scales node style with coverage', () => {
    const low = coverageNodeStyle(15)
    const high = coverageNodeStyle(82)
    expect(high.size).toBeGreaterThan(low.size)
    expect(high.opacity).toBeGreaterThan(low.opacity)
    expect(high.glow).toBeGreaterThan(low.glow)
  })

  it('builds label without corridor or 路口 suffix', () => {
    const html = buildCorrelateLabelHtml({
      inter_id: 'u1',
      name: '经十路辅路与洪山路路口',
      center: [1, 1],
      role: 'upstream',
      path_coverage: 81.8,
      cor_f_dir8_no: 2,
      cor_turn_dir_no: 2,
      links: [],
    })
    expect(html).toContain('经十路辅路与洪山路')
    expect(html).not.toContain('路口')
    expect(html).not.toContain('走廊')
    expect(html).not.toContain('其他向')
    expect(html).toContain('东直行')
    expect(html).toContain('81.8%')
  })

  it('filters upstream below min path coverage or without links', () => {
    expect(MIN_PATH_COVERAGE).toBe(5)
    expect(
      isRenderableUpstream({
        inter_id: 'u1',
        name: '低占比',
        center: [1, 1],
        role: 'upstream',
        path_coverage: 4.9,
        links: [{ link_id: 'l1', link_role: 'entrance', path: [[1, 1], [2, 2]] }],
      }),
    ).toBe(false)
    expect(
      isRenderableUpstream({
        inter_id: 'u2',
        name: '有效',
        center: [1, 1],
        role: 'upstream',
        path_coverage: 5,
        links: [{ link_id: 'l1', link_role: 'entrance', path: [[1, 1], [2, 2]] }],
      }),
    ).toBe(true)
    expect(
      isRenderableUpstream({
        inter_id: 'u3',
        name: '无 link',
        center: [1, 1],
        role: 'upstream',
        path_coverage: 20,
        links: [],
      }),
    ).toBe(false)
  })

  it('picks main corridor hop1 as default open id', () => {
    const map: UpstreamCorrelateMap = {
      approach: '西进口',
      dir8_code: 6,
      main_corridor_chain: [
        { hop: 1, inter_id: 'hop1', name: '上游一', path_coverage: 90 },
        { hop: 2, inter_id: 'hop2', name: '上游二', path_coverage: 70 },
      ],
      intersections: [],
    }
    expect(defaultOpenUpstreamId(map)).toBe('hop1')
  })
})
