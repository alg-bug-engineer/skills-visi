<script setup lang="ts">
import { computed, ref } from 'vue'
import { logger, type LogEntry, type LogLevel } from '../utils/logger'

const props = defineProps<{
  entries: readonly LogEntry[]
}>()

const expanded = ref(true)
const filterLevel = ref<LogLevel | 'all'>('all')
const filterCategory = ref('')

const levelOptions: Array<LogLevel | 'all'> = ['all', 'debug', 'info', 'warn', 'error']

const filtered = computed(() => {
  return props.entries.filter((e) => {
    if (filterLevel.value !== 'all' && e.level !== filterLevel.value) return false
    if (filterCategory.value && !e.category.includes(filterCategory.value)) return false
    return true
  })
})

const levelClass: Record<LogLevel, string> = {
  debug: 'lvl-debug',
  info: 'lvl-info',
  warn: 'lvl-warn',
  error: 'lvl-error',
}

function formatTime(iso: string) {
  return iso.slice(11, 23)
}

function exportLogs() {
  const blob = new Blob([JSON.stringify(props.entries, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `frontend-logs-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="log-panel">
    <header class="log-header" @click="expanded = !expanded">
      <div class="log-title">
        <span class="chevron" :class="{ open: expanded }">▸</span>
        <h3>调试日志</h3>
        <span class="count">{{ filtered.length }} 条</span>
      </div>
      <div class="log-actions" @click.stop>
        <select v-model="filterLevel" class="filter-select">
          <option v-for="opt in levelOptions" :key="opt" :value="opt">
            {{ opt === 'all' ? '全部级别' : opt }}
          </option>
        </select>
        <input
          v-model="filterCategory"
          class="filter-input"
          placeholder="筛选 category"
        />
        <button type="button" class="btn-sm" @click="logger.clear()">清空</button>
        <button type="button" class="btn-sm" @click="exportLogs">导出</button>
      </div>
    </header>

    <div v-show="expanded" class="log-body">
      <p v-if="!filtered.length" class="empty">暂无日志。API 请求、SSE 事件、会话状态变化会记录在此。</p>
      <div
        v-for="entry in [...filtered].reverse()"
        :key="entry.id"
        :class="['log-row', levelClass[entry.level]]"
      >
        <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
        <span class="log-level">{{ entry.level }}</span>
        <span class="log-cat">{{ entry.category }}</span>
        <span class="log-msg">{{ entry.message }}</span>
        <details v-if="entry.data !== undefined" class="log-data">
          <summary>data</summary>
          <pre>{{ JSON.stringify(entry.data, null, 2) }}</pre>
        </details>
      </div>
    </div>
  </section>
</template>

<style scoped>
.log-panel {
  border-top: 1px solid #334155;
  background: #0b1220;
  color: #cbd5e1;
  max-height: 220px;
  display: flex;
  flex-direction: column;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  cursor: pointer;
  background: #111827;
  flex-shrink: 0;
}

.log-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-title h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.count {
  font-size: 11px;
  color: #64748b;
  padding: 2px 6px;
  background: #1e293b;
  border-radius: 4px;
}

.chevron {
  display: inline-block;
  transition: transform 0.15s;
  color: #64748b;
}

.chevron.open {
  transform: rotate(90deg);
}

.log-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.filter-select,
.filter-input {
  font-size: 11px;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
}

.filter-input {
  width: 110px;
}

.btn-sm {
  font-size: 11px;
  padding: 4px 8px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #1e293b;
  color: #94a3b8;
  cursor: pointer;
}

.btn-sm:hover {
  background: #334155;
  color: #e2e8f0;
}

.log-body {
  overflow-y: auto;
  flex: 1;
  padding: 6px 10px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 11px;
}

.empty {
  margin: 8px;
  color: #64748b;
  font-family: inherit;
  font-size: 12px;
}

.log-row {
  display: grid;
  grid-template-columns: 72px 48px 100px 1fr;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  align-items: start;
}

.log-row:hover {
  background: #111827;
}

.lvl-error .log-level {
  color: #f87171;
}
.lvl-warn .log-level {
  color: #fbbf24;
}
.lvl-info .log-level {
  color: #38bdf8;
}
.lvl-debug .log-level {
  color: #64748b;
}

.log-time {
  color: #475569;
}

.log-cat {
  color: #22d3ee;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg {
  word-break: break-all;
}

.log-data {
  grid-column: 1 / -1;
  margin: 0 0 4px 72px;
}

.log-data summary {
  cursor: pointer;
  color: #64748b;
}

.log-data pre {
  margin: 4px 0 0;
  padding: 6px;
  background: #020617;
  border-radius: 4px;
  overflow-x: auto;
  max-height: 120px;
}
</style>
