export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

type Task = () => Promise<void>

export class AnalysisQueue {
  private chain: Promise<void> = Promise.resolve()
  private running = false
  private paused = false
  private resumeWaiters: Array<() => void> = []

  enqueue(task: Task, pauseMs = 0): void {
    this.chain = this.chain.then(async () => {
      await this.waitWhilePaused()
      this.running = true
      await task()
      if (pauseMs > 0) await sleep(pauseMs)
      this.running = false
    })
  }

  get isRunning(): boolean {
    return this.running
  }

  whenIdle(): Promise<void> {
    return this.chain
  }

  reset(): void {
    this.chain = Promise.resolve()
    this.running = false
    this.resume()
  }

  pause(): void {
    this.paused = true
  }

  resume(): void {
    this.paused = false
    const waiters = [...this.resumeWaiters]
    this.resumeWaiters = []
    waiters.forEach((resolve) => resolve())
  }

  private waitWhilePaused(): Promise<void> {
    if (!this.paused) return Promise.resolve()
    return new Promise((resolve) => {
      this.resumeWaiters.push(resolve)
    })
  }
}
