<script setup lang="ts">
import { computed } from 'vue'
import type { DataWindowMeta, StepRecord } from '../types/api'
import { formatDataWindowSummary } from '../utils/dataWindow'

const props = defineProps<{
  steps: StepRecord[]
  active: boolean
}>()

const statusIcon: Record<string, string> = {
  running: '⏳',
  completed: '✅',
  failed: '❌',
}

const latestRunning = computed(() => {
  const running = [...props.steps].reverse().find((s) => s.status === 'running')
  return running?.label ?? (props.active ? '智能体思考中…' : '等待输入')
})

const dataWindowSummary = computed(() => {
  const fetchStep = [...props.steps].reverse().find((s) => s.step === 'data_fetch' && s.status === 'completed')
  const dw = fetchStep?.data?.data_window as DataWindowMeta | undefined
  return dw ? formatDataWindowSummary(dw) : null
})

function stepSummary(item: StepRecord): string | null {
  if (item.step !== 'data_fetch' || item.status !== 'completed') return null
  const dw = item.data?.data_window as DataWindowMeta | undefined
  return dw ? formatDataWindowSummary(dw) : null
}
</script>

<template>
  <aside class="execution-panel">
    <header class="panel-header">
      <h2>执行过程</h2>
      <span v-if="active" class="pulse-dot" title="执行中" />
    </header>

    <p class="current-step">{{ latestRunning }}</p>

    <div v-if="dataWindowSummary" class="data-window-card">
      <span class="dw-title">数据时间窗</span>
      <p class="dw-text">{{ dataWindowSummary }}</p>
    </div>

    <ol v-if="steps.length" class="step-list">
      <li
        v-for="(item, idx) in steps"
        :key="`${item.step}-${idx}`"
        :class="['step-item', `status-${item.status}`]"
      >
        <span class="step-icon">{{ statusIcon[item.status] ?? '•' }}</span>
        <div class="step-body">
          <span class="step-label">{{ item.label }}</span>
          <p v-if="stepSummary(item)" class="step-summary">{{ stepSummary(item) }}</p>
          <details v-if="item.data && Object.keys(item.data).length" class="step-details">
            <summary>详情</summary>
            <pre>{{ JSON.stringify(item.data, null, 2) }}</pre>
          </details>
        </div>
      </li>
    </ol>

    <p v-else class="empty-hint">发送消息后，此处将实时展示 NLU、数据查询、规则诊断等步骤。</p>
  </aside>
</template>

<style scoped>
.execution-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 20px;
  background: #0f172a;
  color: #e2e8f0;
  border-left: 1px solid #1e293b;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22d3ee;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

.current-step {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #1e293b;
  font-size: 13px;
  color: #94a3b8;
}

.data-window-card {
  padding: 10px 12px;
  border-radius: 8px;
  background: #172554;
  border: 1px solid #1e40af;
}

.dw-title {
  font-size: 11px;
  color: #93c5fd;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dw-text {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #dbeafe;
}

.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  background: #111827;
  border: 1px solid transparent;
  font-size: 13px;
}

.step-item.status-running {
  border-color: #0891b2;
}

.step-item.status-failed {
  border-color: #dc2626;
}

.step-icon {
  flex-shrink: 0;
  line-height: 1.4;
}

.step-body {
  flex: 1;
  min-width: 0;
}

.step-label {
  display: block;
  font-weight: 500;
}

.step-summary {
  margin: 4px 0 0;
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.4;
}

.step-details {
  margin-top: 6px;
}

.step-details summary {
  cursor: pointer;
  color: #64748b;
  font-size: 12px;
}

.step-details pre {
  margin: 6px 0 0;
  padding: 8px;
  border-radius: 6px;
  background: #0b1220;
  font-size: 11px;
  overflow-x: auto;
  max-height: 160px;
}

.empty-hint {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}
</style>
