import { describe, expect, it } from 'vitest'
import {
  buildSegmentCoverageLabelHtml,
  buildSegmentCoverageLinkHtml,
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
    expect(inter).toContain('1/2趟 (50.0%)')
    expect(link).toContain('齐川路')
    expect(link).toContain('1/2趟 (50.0%)')
  })
})
