import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { createPresentationBarrier } from './usePresentationBarrier'
import { createInitialAbsorptionState } from '../types/skillAbsorption'

describe('createPresentationBarrier', () => {
  it('waits for process and voice before settling', async () => {
    let processDone = false
    let voiceDone = false
    const voiceWhenIdle = () =>
      new Promise<void>((resolve) => {
        const tick = () => {
          if (voiceDone) resolve()
          else setTimeout(tick, 10)
        }
        tick()
      })

    const barrier = createPresentationBarrier({
      whenProcessIdle: () =>
        new Promise<void>((resolve) => {
          const tick = () => {
            if (processDone) resolve()
            else setTimeout(tick, 10)
          }
          tick()
        }),
      voice: { enabled: ref(true), whenIdle: voiceWhenIdle },
      getAbsorptionState: () => createInitialAbsorptionState(),
    })

    const settled = barrier.whenSettled()
    setTimeout(() => {
      processDone = true
    }, 30)
    setTimeout(() => {
      voiceDone = true
    }, 60)

    await settled
    expect(processDone && voiceDone).toBe(true)
  })

  it('skips voice wait when disabled', async () => {
    const barrier = createPresentationBarrier({
      whenProcessIdle: async () => {},
      voice: { enabled: ref(false), whenIdle: () => Promise.reject(new Error('should not run')) },
      getAbsorptionState: () => createInitialAbsorptionState(),
    })
    await expect(barrier.whenSettled()).resolves.toBeUndefined()
  })
})
