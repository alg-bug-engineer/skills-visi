import { describe, expect, it } from 'vitest'
import { productCopy } from '@/utils/productCopy'
import { t } from '@/labels/enums'

describe('product copy sanitization', () => {
  it('rewrites internal/debug phrasing into production wording', () => {
    const copy = productCopy('校验问题：加绿以后，车有没有地方去？相位差匹配：pg')

    expect(copy).not.toContain('校验问题')
    expect(copy).not.toContain('车有没有地方去')
    expect(copy).not.toContain('pg')
    expect(copy).toContain('下游承接空间')
    expect(copy).toContain('真实信控数据')
  })

  it('does not expose PG as a user-facing data source label', () => {
    expect(t('data_source', 'pg')).toBe('真实信控数据')
  })
})
