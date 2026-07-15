import { describe, expect, it } from 'vitest'
import {
  buildSegmentCoverageLabelHtml,
  buildSegmentCoverageLinkHtml,
  buildSegmentCoverageTargetHtml,
  formatCoverageShare,
} from '@/map/traceCoverageLabel'

describe('traceCoverageLabel', () => {
  it('formats coverage as percent without trip counts', () => {
    expect(formatCoverageShare({ ratio: 0.573, flow: 573, targetFlow: 1000 })).toBe('57.3%')
    expect(formatCoverageShare({ ratio: 0.5, flow: 1, targetFlow: 2 })).toBe('50.0%')
    expect(formatCoverageShare({ ratio: 0.5, targetFlow: 2 })).toBe('50.0%')
  })

  it('uses consistent intersection/link label metrics', () => {
    const inter = buildSegmentCoverageLabelHtml({
      name: '书昌街与齐音路路口',
      ratio: 0.5,
      flow: 1,
      targetFlow: 2,
      kind: 'intersection',
    })
    const link = buildSegmentCoverageLinkHtml({
      name: '齐川路',
      ratio: 0.5,
      flow: 1,
      targetFlow: 2,
    })
    expect(inter).toContain('书昌街与齐音路路口')
    expect(inter).toContain('占目标流量')
    expect(inter).not.toContain('途经')
    expect(inter).not.toContain('趟')
    expect(link).toContain('齐川路')
    expect(link).toContain('占目标流向 50.0%')
    expect(link).not.toContain('覆盖')
    expect(link).not.toContain('趟')
  })

  it('does not show low-sample trip disclaimer on target label', () => {
    const html = buildSegmentCoverageTargetHtml({
      name: '解放东路与齐川路路口',
      targetFlow: 2,
      lowSample: true,
    })
    expect(html).toContain('目标：解放东路与齐川路路口')
    expect(html).not.toContain('样本')
    expect(html).not.toContain('仅供示意')
    expect(html).not.toContain('趟')
  })
})
