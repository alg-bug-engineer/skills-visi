import { describe, expect, it, vi } from 'vitest'
import { buildToastCopy, useAbsorptionToasts } from './useAbsorptionToasts'

describe('buildToastCopy', () => {
  it('cognition verified + inserted', () => {
    const { header, footer } = buildToastCopy({
      kind: 'cognition',
      status: 'verified',
      action: 'inserted',
      tags: [],
    })
    expect(header).toBe('已验证用户提供的路口认知经验')
    expect(footer).toBe('已插入该路口认知经验库')
  })

  it('cognition data_doubt + updated', () => {
    const { header, footer } = buildToastCopy({
      kind: 'cognition',
      status: 'data_doubt',
      action: 'updated',
      tags: [],
    })
    expect(header).toContain('未找到数据支撑')
    expect(footer).toBe('已更新该路口认知经验库')
  })

  it('cognition exists', () => {
    expect(buildToastCopy({ kind: 'cognition', status: 'verified', action: 'exists', tags: [] }).footer).toBe(
      '已存在该路口认知经验库',
    )
  })

  it('diagnosis inserted is absorbed-and-stored', () => {
    const { header, footer } = buildToastCopy({ kind: 'diagnosis', action: 'inserted', tags: [] })
    expect(header).toBe('已吸收用户提供的诊断经验并入库')
    expect(footer).toBe('已并入该路口诊断经验库')
  })

  it('diagnosis exists → not re-inserted/updated', () => {
    expect(buildToastCopy({ kind: 'diagnosis', action: 'exists', tags: [] }).footer).toBe(
      '该诊断经验已存在（不再插入/更新）',
    )
  })
})

describe('useAbsorptionToasts', () => {
  it('push enqueues with computed copy and dismiss removes', () => {
    const { toasts, push, dismiss } = useAbsorptionToasts(0)
    const t = push({ kind: 'cognition', status: 'verified', action: 'inserted', tags: ['认知画像'] })
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].header).toBe('已验证用户提供的路口认知经验')
    dismiss(t.id)
    expect(toasts.value).toHaveLength(0)
  })

  it('auto-dismisses after timeout', () => {
    vi.useFakeTimers()
    const { toasts, push } = useAbsorptionToasts(1000)
    push({ kind: 'diagnosis', action: 'inserted', tags: [] })
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(1000)
    expect(toasts.value).toHaveLength(0)
    vi.useRealTimers()
  })
})
