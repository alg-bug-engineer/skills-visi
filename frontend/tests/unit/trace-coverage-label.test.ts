import { describe, expect, it } from 'vitest'
import {
  buildSegmentCoverageLabelHtml,
  buildSegmentCoverageLinkHtml,
  buildSegmentCoverageTargetHtml,
  formatCoverageShare,
} from '@/map/traceCoverageLabel'

describe('traceCoverageLabel', () => {
  it('formats normal sample as percent', () => {
    expect(formatCoverageShare({ ratio: 0.573, flow: 573, targetFlow: 1000 })).toBe('57.3%')
  })

  it('shows trip counts for low sample instead of bare 50%', () => {
    expect(formatCoverageShare({ ratio: 0.5, flow: 1, targetFlow: 2 })).toBe('1/2趟 (50.0%)')
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
    expect(link).toContain('齐川路')
    expect(link).toContain('1/2趟 (50.0%)')
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
  })

  it('omits bare sample count when flow is unknown', () => {
    expect(formatCoverageShare({ ratio: 0.5, targetFlow: 2 })).toBe('约50.0%')
  })
})
