import { describe, expect, it, vi } from 'vitest'
import { AnalysisQueue } from './analysisQueue'

/** RT-PAUSE-BOUNDARY: pause blocks next task until resume; current task completes. */
describe('AnalysisQueue pause', () => {
  it('runs current task to completion then blocks the next until resume', async () => {
    const queue = new AnalysisQueue()
    const order: string[] = []

    queue.enqueue(async () => {
      order.push('a-start')
      await new Promise((r) => setTimeout(r, 20))
      order.push('a-end')
      queue.pause()
    })

    queue.enqueue(async () => {
      order.push('b')
    })

    await new Promise((r) => setTimeout(r, 60))
    expect(order).toEqual(['a-start', 'a-end'])

    queue.resume()
    await queue.whenIdle()
    expect(order).toEqual(['a-start', 'a-end', 'b'])
  })

  it('reset clears pause waiters', async () => {
    const queue = new AnalysisQueue()
    queue.pause()
    queue.reset()
    const fn = vi.fn()
    queue.enqueue(async () => {
      fn()
    })
    await queue.whenIdle()
    expect(fn).toHaveBeenCalledOnce()
  })
})
