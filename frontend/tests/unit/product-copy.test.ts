import { describe, expect, it } from 'vitest'
import { productCopy } from '@/utils/productCopy'

describe('productCopy · 枚举中文化', () => {
  it('translates snake_case codes in plain text', () => {
    expect(productCopy('downstream_protection')).toBe('下游保护方案')
    expect(productCopy('策略包 incremental_release')).toBe('策略包 目标路口小步释放方案')
  })

  it('replaces corridor with 干线', () => {
    expect(productCopy('corridor 瓶颈')).toBe('干线 瓶颈')
  })
})
