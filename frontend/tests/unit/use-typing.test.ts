import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useTyping } from '@/composables/useTyping'

describe('useTyping · restartKey', () => {
  it('lines 变化但 restartKey 不变时不重启', async () => {
    const lines = ref(['第一行'])
    const key = ref('act-0')
    let doneCount = 0

    useTyping(lines, {
      instant: true,
      restartKey: key,
      onDone: () => {
        doneCount++
      },
    })

    expect(doneCount).toBe(1)
    lines.value = ['第一行', '第二行']
    await nextTick()
    expect(doneCount).toBe(1)

    key.value = 'act-1'
    await nextTick()
    expect(doneCount).toBe(2)
  })
})

describe('useTyping · paused', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('paused=true 时暂停逐字输出', async () => {
    const lines = ref(['ab'])
    const paused = ref(false)
    let finished = false

    const { shown, done } = useTyping(lines, {
      speed: 20,
      paused,
      onDone: () => {
        finished = true
      },
    })

    await vi.advanceTimersByTimeAsync(25)
    expect(shown.value[0]).toBe('a')
    paused.value = true
    await vi.advanceTimersByTimeAsync(100)
    expect(shown.value[0]).toBe('a')
    paused.value = false
    await vi.advanceTimersByTimeAsync(100)
    expect(shown.value[0]).toBe('ab')
    expect(done.value).toBe(true)
    expect(finished).toBe(true)
  })
})
