import type { ExecutionStepEvent, MessageResponse, SseStreamEvent } from '../types/api'
import type { SkillBuildEvent } from '../types/skillBuild'
import type { SkillAbsorptionEvent } from '../types/skillAbsorption'
import { logger } from '../utils/logger'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

const HEALTH_PATHS = ['/api/v1/health', '/health'] as const

function buildUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function requestJson<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<{ data: T; status: number; url: string }> {
  const url = buildUrl(path)
  const started = performance.now()
  logger.info('api', `${method} ${path}`, { url, body })

  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  })

  const elapsed = Math.round(performance.now() - started)
  const text = await res.text()
  let parsed: unknown = text
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    /* keep raw text */
  }

  logger.info('api', `${method} ${path} → ${res.status} (${elapsed}ms)`, {
    url,
    status: res.status,
    elapsed_ms: elapsed,
    response: parsed,
    request_id: res.headers.get('X-Request-ID'),
  })

  if (!res.ok) {
    logger.error('api', `请求失败 ${method} ${path}`, { status: res.status, url, body: parsed })
    throw new Error(`请求失败 ${res.status}: ${typeof parsed === 'string' ? parsed : JSON.stringify(parsed)}`)
  }

  return { data: parsed as T, status: res.status, url }
}

export async function fetchSkillLeaderboard(
  sort: 'hits' | 'created' | 'updated' = 'hits',
): Promise<import('../types/skillLeaderboard').SkillLeaderboardItem[]> {
  const { data } = await requestJson<import('../types/skillLeaderboard').SkillLeaderboardItem[]>(
    'GET',
    `/api/v1/skills/leaderboard?sort=${sort}`,
  )
  return data
}

export async function createSession(): Promise<{ session_id: string; state: string }> {
  const { data } = await requestJson<{ session_id: string; state: string }>('POST', '/api/v1/sessions')
  logger.info('session', '会话已创建', data)
  return data
}

export async function checkHealth(): Promise<Record<string, unknown>> {
  const errors: Array<{ path: string; url: string; status: number; body: unknown }> = []

  for (const path of HEALTH_PATHS) {
    const url = buildUrl(path)
    logger.info('health', `探测 ${path}`, { url })
    try {
      const res = await fetch(url)
      const text = await res.text()
      let body: unknown = text
      try {
        body = text ? JSON.parse(text) : null
      } catch {
        /* raw */
      }

      if (res.ok) {
        logger.info('health', `健康检查成功 ${path}`, { url, status: res.status, body })
        return body as Record<string, unknown>
      }

      errors.push({ path, url, status: res.status, body })
      logger.warn('health', `${path} 返回 ${res.status}`, { url, body })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      errors.push({ path, url, status: 0, body: message })
      logger.warn('health', `${path} 网络错误`, { url, error: message })
    }
  }

  const hint =
    '请运行一键启动脚本: bash scripts/dev-v2.sh（后端 8011 / 前端 5568）。' +
    '或手动启动: cd backend && source .venv/bin/activate && uvicorn intersection_agent.main:app --host 127.0.0.1 --port 8011'

  logger.error('health', '所有健康检查路径均失败', { errors, hint })
  throw new Error(
    `健康检查失败（已尝试 ${errors.map((e) => `${e.path}→${e.status}`).join(', ')}）。${hint}`,
  )
}

export type StreamCallbacks = {
  onStep: (event: ExecutionStepEvent) => void
  onSkillBuild?: (event: SkillBuildEvent) => void
  onSkillAbsorption?: (event: SkillAbsorptionEvent) => void
  onResult: (result: MessageResponse) => void
  onError: (message: string, detail?: string) => void
}

/** POST + SSE: stream execution steps then final result. */
export async function sendMessageStream(
  sessionId: string,
  content: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const path = `/api/v1/sessions/${sessionId}/messages/stream`
  const url = buildUrl(path)
  const started = performance.now()

  logger.info('sse', '开始流式请求', { url, sessionId, content_length: content.length })

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  })

  if (!res.ok) {
    const text = await res.text()
    logger.error('sse', `流式请求失败 ${res.status}`, { url, body: text })
    throw new Error(`请求失败 ${res.status}: ${text}`)
  }

  logger.info('sse', 'SSE 连接已建立', {
    url,
    content_type: res.headers.get('Content-Type'),
    request_id: res.headers.get('X-Request-ID'),
  })

  const reader = res.body?.getReader()
  if (!reader) throw new Error('浏览器不支持流式响应')

  const decoder = new TextDecoder()
  let buffer = ''
  let eventCount = 0
  let gotResult = false
  let gotDone = false
  let gotError = false

  const handleEvent = (event: SseStreamEvent) => {
    eventCount += 1
    logger.debug('sse', `事件 #${eventCount} ${event.event}`, event)

    if (event.event === 'step') {
      logger.info('step', `${event.step} · ${event.status}`, {
        label: event.label,
        data: event.data,
      })
      callbacks.onStep(event)
    } else if (event.event === 'skill_build') {
      logger.info('skill_build', `${event.type} · ${event.stage}`, event.payload)
      callbacks.onSkillBuild?.(event as SkillBuildEvent)
    } else if (event.event === 'skill_absorption') {
      logger.info('skill_absorption', `${event.type} · ${event.stage}`, event.payload)
      callbacks.onSkillAbsorption?.(event as SkillAbsorptionEvent)
    } else if (event.event === 'result') {
      gotResult = true
      const result = event.data as unknown as MessageResponse
      logger.info('sse', '收到最终结果', {
        state: result.state,
        reply_type: result.reply?.type,
      })
      callbacks.onResult(result)
    } else if (event.event === 'error') {
      gotError = true
      logger.error('sse', '服务端错误事件', event)
      callbacks.onError(event.message ?? '未知错误', event.detail)
    } else if (event.event === 'done') {
      gotDone = true
      logger.info('sse', '流结束', { event_count: eventCount })
    }
  }

  const parseBuffer = () => {
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const block of parts) {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (!raw.trim()) continue
        handleEvent(JSON.parse(raw) as SseStreamEvent)
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    buffer += chunk
    logger.debug('sse', '收到数据块', { bytes: value.byteLength, preview: chunk.slice(0, 200) })
    parseBuffer()
  }

  buffer += decoder.decode()
  parseBuffer()

  if (!gotResult && !gotError) {
    const detail = gotDone
      ? '分析流已结束，但未收到完整结果'
      : '连接意外断开，分析未完成'
    logger.error('sse', detail, { event_count: eventCount, got_done: gotDone })
    callbacks.onError('分析中断', detail)
  }

  const elapsed = Math.round(performance.now() - started)
  logger.info('sse', `流式请求完成 (${elapsed}ms)`, { event_count: eventCount, elapsed_ms: elapsed })
}
