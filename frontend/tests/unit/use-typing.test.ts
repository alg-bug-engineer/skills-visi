import { describe, expect, it } from 'vitest'
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
