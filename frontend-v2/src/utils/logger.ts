import { reactive, readonly } from 'vue'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEntry {
  id: string
  level: LogLevel
  category: string
  message: string
  data?: unknown
  timestamp: string
}

const MAX_ENTRIES = 500

const state = reactive({
  entries: [] as LogEntry[],
  enabled: import.meta.env.DEV || import.meta.env.VITE_DEBUG_LOG === '1',
})

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function consoleWrite(level: LogLevel, category: string, message: string, data?: unknown) {
  const prefix = `[${category}]`
  const args = data !== undefined ? [prefix, message, data] : [prefix, message]
  switch (level) {
    case 'debug':
      console.debug(...args)
      break
    case 'info':
      console.info(...args)
      break
    case 'warn':
      console.warn(...args)
      break
    case 'error':
      console.error(...args)
      break
  }
}

function push(level: LogLevel, category: string, message: string, data?: unknown) {
  const entry: LogEntry = {
    id: uid(),
    level,
    category,
    message,
    data,
    timestamp: new Date().toISOString(),
  }
  state.entries.push(entry)
  if (state.entries.length > MAX_ENTRIES) {
    state.entries.splice(0, state.entries.length - MAX_ENTRIES)
  }
  if (state.enabled) {
    consoleWrite(level, category, message, data)
  }
}

export const logger = {
  get entries() {
    return readonly(state.entries)
  },
  get enabled() {
    return state.enabled
  },
  debug: (category: string, message: string, data?: unknown) => push('debug', category, message, data),
  info: (category: string, message: string, data?: unknown) => push('info', category, message, data),
  warn: (category: string, message: string, data?: unknown) => push('warn', category, message, data),
  error: (category: string, message: string, data?: unknown) => push('error', category, message, data),
  clear() {
    state.entries.splice(0, state.entries.length)
  },
}
