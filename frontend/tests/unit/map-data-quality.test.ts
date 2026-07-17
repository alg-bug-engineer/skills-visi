import { describe, expect, it } from 'vitest'
import { findMockVisualizationPaths } from '@/map/mapDataQuality'

describe('map mock data warning', () => {
  it('递归识别显式 mock/source 且忽略真实 PG 数据', () => {
    const value = {
      real: { source: 'postgresql', path: [[1, 2], [3, 4]] },
      missing: { geometry: { mock: true, source: 'mock_visualization' } },
    }
    expect(findMockVisualizationPaths(value)).toContain('missing.geometry')
    expect(findMockVisualizationPaths(value).some((path) => path.startsWith('real'))).toBe(false)
  })
})
