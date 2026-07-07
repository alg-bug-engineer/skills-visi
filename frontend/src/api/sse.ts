/**
 * SSE 封装：仅 /intersection/load/stream 为真 SSE。
 * 含最多 3 次重连的状态机（F-14），失败回调交由上层切 Mock 兜底。
 */
export type SseStatus = 'connecting' | 'open' | 'closed' | 'error'

export interface SseHandlers {
  onStatus?: (s: SseStatus, attempt: number) => void
  onMessage?: (event: string, data: unknown) => void
  onFail?: () => void
}

export interface SseController {
  close: () => void
}

const MAX_RETRY = 3

// EventSource 仅支持 GET；load/stream 后端为 POST。此封装用于「回滚监听」场景，
// 以轮询/可替换实现兜底；此处提供统一状态机骨架，真实端点可注入 fetcher。
export function openReconnectingStream(
  fetcher: (signal: AbortSignal) => Promise<void>,
  handlers: SseHandlers,
): SseController {
  let attempt = 0
  let stopped = false
  const ctrl = new AbortController()

  const run = async () => {
    while (!stopped && attempt <= MAX_RETRY) {
      handlers.onStatus?.(attempt === 0 ? 'connecting' : 'connecting', attempt)
      try {
        await fetcher(ctrl.signal)
        handlers.onStatus?.('open', attempt)
        return
      } catch {
        attempt += 1
        handlers.onStatus?.('error', attempt)
        if (attempt > MAX_RETRY) {
          handlers.onFail?.()
          handlers.onStatus?.('closed', attempt)
          return
        }
        await new Promise((r) => setTimeout(r, 800 * attempt))
      }
    }
  }
  void run()

  return {
    close() {
      stopped = true
      ctrl.abort()
      handlers.onStatus?.('closed', attempt)
    },
  }
}
